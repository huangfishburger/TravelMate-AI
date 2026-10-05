def check_budget(total_budget, costs):
    total_cost = sum(costs.values())

    return {
        "budget": total_budget,
        "total_cost": total_cost,
        "remaining": total_budget - total_cost,
        "within_budget": total_cost <= total_budget
    }