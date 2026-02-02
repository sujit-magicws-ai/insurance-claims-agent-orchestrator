# Shared package for common utilities
# Contains data models, prompts, and agent client helpers

from .models import (
    # Agent1 Models
    Agent1Input,
    Agent1Output,
    ClaimClassification,
    ExtractedInfo,
    Agent1Flags,
    # HITL Models
    ApprovalDecision,
    ClaimAmounts,
    # Agent2 Models
    Agent2Output,
    EvaluationSummary,
    # Orchestration Models
    ClaimRequest,
    OrchestrationResult,
)

from .prompts import (
    AGENT1_SYSTEM_PROMPT,
    AGENT1_USER_PROMPT_TEMPLATE,
    AGENT2_SYSTEM_PROMPT,
    AGENT2_USER_PROMPT_TEMPLATE,
    build_agent1_prompt,
    build_agent2_prompt,
)

from .agent_client import (
    get_credential,
    is_mock_mode,
    invoke_foundry_agent,
    invoke_agent1,
    invoke_agent2,
)

__all__ = [
    # Agent1 Models
    "Agent1Input",
    "Agent1Output",
    "ClaimClassification",
    "ExtractedInfo",
    "Agent1Flags",
    # HITL Models
    "ApprovalDecision",
    "ClaimAmounts",
    # Agent2 Models
    "Agent2Output",
    "EvaluationSummary",
    # Orchestration Models
    "ClaimRequest",
    "OrchestrationResult",
    # Prompts
    "AGENT1_SYSTEM_PROMPT",
    "AGENT1_USER_PROMPT_TEMPLATE",
    "AGENT2_SYSTEM_PROMPT",
    "AGENT2_USER_PROMPT_TEMPLATE",
    "build_agent1_prompt",
    "build_agent2_prompt",
    # Agent Client
    "get_credential",
    "is_mock_mode",
    "invoke_foundry_agent",
    "invoke_agent1",
    "invoke_agent2",
]
