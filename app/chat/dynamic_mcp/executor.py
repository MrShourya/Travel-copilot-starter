from typing import Any

from app.chat.dynamic_mcp.models import ExecutionResult, PlannerDecision
from app.chat.dynamic_mcp.tool_catalog import get_required_args, get_tool_spec
from app.mcp.currency_client import CurrencyMCPClient
from app.mcp.travel_planning_client import TravelPlanningMCPClient
from app.mcp.weather_client import WeatherMCPClient

weather_client = WeatherMCPClient()
currency_client = CurrencyMCPClient()
travel_planning_client = TravelPlanningMCPClient()


def _normalize_args(arguments: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in arguments.items() if v is not None}


def _missing_required_fields(
    available_tools: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
) -> list[str]:
    required = get_required_args(available_tools, tool_name)
    missing = []

    for field in required:
        value = arguments.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)

    return missing


def _build_followup_question(missing_fields: list[str], tool_name: str | None) -> str:
    friendly = {
        "city": "Which city should I use?",
        "trip_days": "How many days should the trip cover?",
        "date_text": "When is the trip?",
        "start_date": "What is the start date?",
        "end_date": "What is the end date?",
        "season": "Which season should I use?",
        "budget_amount": "What budget should I use?",
        "budget_currency": "Which budget currency should I use?",
        "target_currency": "Which currency should I show the result in?",
        "base": "Which source currency should I use?",
        "symbols": "Which target currency should I convert to?",
    }

    if not missing_fields:
        return "I need one more detail before I can continue."

    if len(missing_fields) == 1:
        return friendly.get(missing_fields[0], f"Please provide {missing_fields[0]}.")

    questions = [friendly.get(field, f"Please provide {field}.") for field in missing_fields]
    return " ".join(questions)


def explain_validation(
    decision: PlannerDecision,
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    if decision.action != "call_tool":
        return {
            "selected_action": decision.action,
            "tool_name": decision.tool_name,
            "required_args": [],
            "provided_args": decision.arguments,
            "missing_args": [],
        }

    required_args = get_required_args(available_tools, decision.tool_name)
    provided_args = decision.arguments or {}
    missing_args = _missing_required_fields(available_tools, decision.tool_name, provided_args)

    return {
        "selected_action": decision.action,
        "tool_name": decision.tool_name,
        "required_args": required_args,
        "provided_args": provided_args,
        "missing_args": missing_args,
    }


def validate_planner_decision(
    decision: PlannerDecision,
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    if decision.action == "ask_user":
        if not decision.question:
            return {
                "ok": False,
                "error": "ask_user action requires question.",
                "missing_fields": decision.missing_fields,
            }
        return {"ok": True, "missing_fields": decision.missing_fields}

    if decision.action == "answer":
        if not decision.final_answer:
            return {
                "ok": False,
                "error": "answer action requires final_answer.",
                "missing_fields": [],
            }
        return {"ok": True, "missing_fields": []}

    if decision.action == "call_tool":
        if not decision.tool_name:
            return {
                "ok": False,
                "error": "call_tool action requires tool_name.",
                "missing_fields": [],
            }

        spec = get_tool_spec(available_tools, decision.tool_name)
        if spec is None:
            return {
                "ok": False,
                "error": f"Unknown tool: {decision.tool_name}",
                "missing_fields": [],
            }

        missing = _missing_required_fields(
            available_tools,
            decision.tool_name,
            decision.arguments,
        )
        if missing:
            return {
                "ok": False,
                "error": f"Missing required arguments for {decision.tool_name}",
                "missing_fields": missing,
            }

        return {"ok": True, "missing_fields": []}

    return {"ok": False, "error": f"Unknown action: {decision.action}", "missing_fields": []}


async def execute_planner_tool(decision: PlannerDecision) -> ExecutionResult:
    if decision.action != "call_tool":
        return ExecutionResult(
            ok=False,
            tool_name=decision.tool_name,
            mcp_family=decision.mcp_family,
            arguments=decision.arguments,
            error="Decision action is not call_tool.",
        )

    tool_name = decision.tool_name
    arguments = _normalize_args(decision.arguments)
    mcp_family = decision.mcp_family

    if mcp_family == "travel_planning_mcp":
        result = await travel_planning_client.call_tool(tool_name=tool_name, arguments=arguments)
        return ExecutionResult(
            ok=True,
            tool_name=tool_name,
            mcp_family=mcp_family,
            arguments=arguments,
            result=result.content,
        )

    if mcp_family == "weather_mcp":
        result = await weather_client.call_tool(tool_name=tool_name, arguments=arguments)
        return ExecutionResult(
            ok=True,
            tool_name=tool_name,
            mcp_family=mcp_family,
            arguments=arguments,
            result=result.content,
        )

    if mcp_family == "currency_mcp":
        result = await currency_client.call_tool(tool_name=tool_name, arguments=arguments)
        return ExecutionResult(
            ok=True,
            tool_name=tool_name,
            mcp_family=mcp_family,
            arguments=arguments,
            result=result.content,
        )

    return ExecutionResult(
        ok=False,
        tool_name=tool_name,
        mcp_family=mcp_family,
        arguments=arguments,
        error=f"Executor does not support MCP family: {mcp_family}",
    )