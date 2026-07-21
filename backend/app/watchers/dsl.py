"""
app/agents/watcher_dsl.py — Generic condition evaluator for Watchers.

Evaluates an Event object's normalized attributes against trigger rules
expressed in JSON DSL.
"""
from __future__ import annotations

import logging
from typing import Any

from app.watchers.models import Event

logger = logging.getLogger(__name__)


def evaluate_condition(condition_json: dict[str, Any], event: Event) -> bool:
    """Evaluate if the event attributes satisfy the JSON DSL condition.

    Condition schema:
        {
            "conjunction": "AND" | "OR",
            "rules": [
                {
                    "field": "sender",
                    "operator": "equals" | "contains" | "not_contains" | "exists" | "greater_than" | "less_than",
                    "value": <any>
                }
            ]
        }
    """
    if not condition_json:
        return True  # If empty or not specified, trigger fires for all events

    conjunction = condition_json.get("conjunction", "AND").upper()
    rules = condition_json.get("rules", [])
    if not rules:
        return True

    results: list[bool] = []
    for rule in rules:
        field = rule.get("field")
        operator = rule.get("operator", "equals").lower()
        target_val = rule.get("value")

        if not field:
            results.append(False)
            continue

        actual_val = event.attributes.get(field)

        try:
            if operator == "equals":
                if isinstance(actual_val, str) and isinstance(target_val, str):
                    results.append(actual_val.strip().lower() == target_val.strip().lower())
                else:
                    results.append(actual_val == target_val)

            elif operator == "not_equals":
                if isinstance(actual_val, str) and isinstance(target_val, str):
                    results.append(actual_val.strip().lower() != target_val.strip().lower())
                else:
                    results.append(actual_val != target_val)

            elif operator == "contains":
                if actual_val is None:
                    results.append(False)
                elif isinstance(actual_val, list):
                    results.append(
                        any(str(target_val).strip().lower() == str(item).strip().lower()
                            for item in actual_val)
                    )
                else:
                    results.append(str(target_val).strip().lower() in str(actual_val).strip().lower())

            elif operator == "not_contains":
                if actual_val is None:
                    results.append(True)
                elif isinstance(actual_val, list):
                    results.append(
                        not any(str(target_val).strip().lower() == str(item).strip().lower()
                                for item in actual_val)
                    )
                else:
                    results.append(str(target_val).strip().lower() not in str(actual_val).strip().lower())

            elif operator == "exists":
                results.append(actual_val is not None)

            elif operator == "greater_than":
                results.append(float(actual_val) > float(target_val))

            elif operator == "less_than":
                results.append(float(actual_val) < float(target_val))

            else:
                logger.warning("Unsupported operator '%s' in rule: %s", operator, rule)
                results.append(False)

        except (ValueError, TypeError) as exc:
            logger.warning(
                "Type mismatch or casting failed evaluating rule %s on event: %s",
                rule,
                exc,
            )
            results.append(False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error evaluating rule %s", rule)
            results.append(False)

    if conjunction == "AND":
        return all(results)
    if conjunction == "OR":
        return any(results)
    return False
