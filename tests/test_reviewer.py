import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from tests.reviewer import review_case, review_status, compact_trace, completion_applicability, has_verified_return_leg
from tests.run_cases import run_case
from tests.test_case_runner import CASES, CONFIG


def sample():
    return {'hard_constraints':[], 'soft_preferences':[],
            'response_behavior':{'status':'pass','evidence':'answer','reason':'focused'},
            'itinerary_quality':{'status':'not_applicable','evidence':'answer','reason':'search'},
            'completeness':[{'name':name,'status':'not_applicable','evidence':'answer','reason':'search'}
                            for name in ['selected_flight','trip_cost_scope','hotel_total','daily_feasibility']],
            'rule_resolutions':[{'name':'semantic_requirements','status':'pass','evidence':'answer','reason':'matches'}]}


class ReviewerTests(unittest.TestCase):
    def test_undated_local_itinerary_does_not_require_bookings(self):
        trace = [{'event': 'evaluation', 'evaluation': {'overall_score': 8}}]
        applicable = completion_applicability(CASES[37], 'Five-day NYC itinerary', trace)
        self.assertEqual(applicable, {'selected_flight': False, 'trip_cost_scope': False,
                                      'hotel_total': False, 'daily_feasibility': True})

    def test_outbound_only_result_does_not_verify_return(self):
        trace = [{'event': 'tool_call', 'name': 'search_flights',
                  'result': {'flights': [{'flights': [{
                      'departure_airport': {'id': 'LAX', 'time': '2026-11-12 08:44'},
                      'arrival_airport': {'id': 'SFO', 'time': '2026-11-12 10:11'}}]}]}}]
        self.assertFalse(has_verified_return_leg(CASES[1], trace))
        trace[0]['result']['flights'][0]['flights'].append({
            'departure_airport': {'id': 'SFO', 'time': '2026-11-15 17:00'},
            'arrival_airport': {'id': 'LAX', 'time': '2026-11-15 18:30'}})
        self.assertTrue(has_verified_return_leg(CASES[1], trace))

    def test_reviewer_cannot_pass_unverified_return(self):
        client = Mock()
        review = sample()
        review['hard_constraints'] = [
            {'requirement': key, 'status': 'met', 'evidence': 'answer',
             'reason': 'matches', 'handling': 'appropriate'}
            for key in CASES[1]['expected']['hard_constraints']]
        review['completeness'] = [
            {'name': name, 'status': 'pass', 'evidence': 'answer', 'reason': 'appears fine'}
            for name in ['selected_flight','trip_cost_scope','hotel_total','daily_feasibility']]
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(review))
        trace = [{'event': 'evaluation', 'evaluation': {'overall_score': 8}},
                 {'event': 'tool_call', 'name': 'search_flights', 'args': {},
                  'result': {'flights': [{'flights': [{
                      'departure_airport': {'id': 'LAX', 'time': '2026-11-12 08:44'},
                      'arrival_airport': {'id': 'SFO', 'time': '2026-11-12 10:11'}}]}]}}]
        result = review_case(client, CASES[1], {'response': 'Full trip'}, trace,
                             [{'name': 'semantic_requirements', 'status': 'unknown'}])
        flight = next(item for item in result['completeness'] if item['name']=='selected_flight')
        self.assertEqual(flight['status'], 'unknown')
        self.assertEqual(result['status'], 'needs_review')

    def test_compaction_keeps_evidence_and_does_not_modify_trace(self):
        trace = [{'event': 'tool_call', 'name': 'search_hotels', 'args': {'adults': 2},
                  'result': {'properties': [{'name': 'Hotel', 'hotel_class': '4-star',
                      'overall_rating': 4.7, 'total_rate': {'extracted_lowest': 300},
                      'gps_coordinates': {'latitude': 47, 'longitude': -122},
                      'images': [{'thumbnail': 'large-image-url'}]}],
                      'search_metadata': {'url': 'large-metadata'}}}]
        result = compact_trace(trace)
        hotel = result[0]['result']['properties'][0]
        self.assertEqual(hotel['hotel_class'], '4-star')
        self.assertEqual(hotel['total_rate']['extracted_lowest'], 300)
        self.assertEqual(hotel['gps_coordinates']['latitude'], 47)
        self.assertNotIn('images', hotel)
        self.assertEqual(result[0]['args']['adults'], 2)
        self.assertIn('images', trace[0]['result']['properties'][0])

    def test_compaction_preserves_all_flights_and_errors(self):
        flights = [{'price': i, 'flights': [{'flight_number': str(i),
                    'departure_airport': {'id': 'SAN', 'time': '06:00'},
                    'arrival_airport': {'id': 'SEA', 'time': '09:00'}}],
                    'layovers': [{'id': 'SFO', 'duration': 60}]} for i in range(20)]
        trace = [{'event': 'tool_call', 'name': 'search_flights', 'args': {},
                  'result': {'flights': flights}},
                 {'event': 'tool_call', 'name': 'search_hotels', 'args': {},
                  'result': {'error': 'No results'}}]
        compact = compact_trace(trace)
        self.assertEqual(len(compact[0]['result']['flights']), 20)
        self.assertEqual(compact[0]['result']['flights'][0]['layovers'][0]['duration'], 60)
        self.assertEqual(compact[1]['result']['error'], 'No results')

    def test_deterministic_failure_cannot_be_overridden(self):
        self.assertEqual(review_status(sample(),[{'status':'fail'}]),'fail')

    def test_unmet_but_appropriately_explained_is_distinct(self):
        review=sample()
        review['hard_constraints']=[{'status':'unmet','handling':'appropriate'}]
        self.assertEqual(review_status(review,[]),'pass')
        review['hard_constraints'][0]['handling']='inappropriate'
        self.assertEqual(review_status(review,[]),'fail')

    def test_unknown_evidence_needs_review(self):
        review=sample()
        review['soft_preferences']=[{'status':'unknown'}]
        self.assertEqual(review_status(review,[]),'needs_review')

    def test_missing_cost_scope_cannot_pass(self):
        review=sample()
        review['completeness'][1]['status']='unknown'
        self.assertEqual(review_status(review,[]),'needs_review')
        review['completeness'][1]['status']='fail'
        self.assertEqual(review_status(review,[]),'fail')

    def test_payload_hides_evaluator_and_checks_coverage(self):
        client=Mock()
        client.responses.create.return_value=SimpleNamespace(output_text=json.dumps(sample()))
        case={'prompt':'Find cafes','expected':{'hard_constraints':{},'soft_preferences':[]}}
        checks=[{'name':'semantic_requirements','status':'unknown'}]
        result=review_case(client,case,{'response':'Cafe','evaluation':{'overall_score':10}},
            [{'event':'evaluation','evaluation':{'overall_score':10}}],checks)
        payload=json.loads(client.responses.create.call_args.kwargs['input'])
        self.assertNotIn('evaluation',payload['final_answer'])
        self.assertEqual(payload['trace_evidence'],[])
        self.assertEqual(result['status'],'pass')
        case['expected']['hard_constraints']={'nonstop_required':True}
        with self.assertRaisesRegex(ValueError,'cover each'):
            review_case(client,case,'Cafe',[],checks)

    def test_reviewer_error_retains_agent_answer(self):
        def reviewer(*args): raise RuntimeError('review unavailable')
        result=run_case(CASES[47],CONFIG,lambda *args,**kwargs:'Cafe options',reviewer)
        self.assertEqual(result['answer'],'Cafe options')
        self.assertEqual(result['semantic_review']['status'],'error')
        self.assertEqual(result['status'],'needs_review')


if __name__=='__main__': unittest.main()
