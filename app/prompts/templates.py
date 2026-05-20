"""Prompt templates for AI agents."""
from typing import Dict, Any, Optional


class PromptTemplate:
    """Template for AI prompts."""
    
    def __init__(self, name: str, template: str, variables: list[str]):
        self.name = name
        self.template = template
        self.variables = variables
    
    def render(self, **kwargs) -> str:
        """Render template with variables."""
        return self.template.format(**kwargs)


# System prompts
SYSTEM_PROMPT = """You are an enterprise AI agent designed to assist users with complex tasks.
Your responsibilities include:
- Providing accurate and helpful information
- Following strict governance and risk policies
- Escalating complex issues appropriately
- Maintaining conversation context
- Being transparent about limitations

Always prioritize user safety and data security."""

# Task-specific prompts
TASK_ANALYSIS_PROMPT = """Analyze the following user request and break it down into actionable steps:

User Request: {user_request}
Context: {context}

Provide a structured analysis including:
1. Main objective
2. Required information
3. Potential risks
4. Recommended approach"""

ESCALATION_PROMPT = """Based on the conversation history, determine if escalation is needed.

Conversation Summary: {summary}
Current Status: {status}
Complexity Level: {complexity_level}

Decision: Should this be escalated to a human agent?
Reasoning: {reasoning}"""

HALLUCINATION_CHECK_PROMPT = """Verify the accuracy of the following statement:

Statement: {statement}
Context: {context}
Knowledge Base: {knowledge_base}

Provide:
1. Confidence score (0-1)
2. Verification status (verified/unverified/contradicted)
3. Sources if verified
4. Recommended actions"""

RISK_ASSESSMENT_PROMPT = """Assess the risk level of the following action:

Action: {action}
User: {user}
Context: {context}

Evaluate:
1. Security risk
2. Compliance risk
3. Operational risk
4. Recommended mitigations"""


class PromptManager:
    """Manage prompt templates."""
    
    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """Load default prompt templates."""
        self.register_template(
            "task_analysis",
            TASK_ANALYSIS_PROMPT,
            ["user_request", "context"]
        )
        self.register_template(
            "escalation",
            ESCALATION_PROMPT,
            ["summary", "status", "complexity_level", "reasoning"]
        )
        self.register_template(
            "hallucination_check",
            HALLUCINATION_CHECK_PROMPT,
            ["statement", "context", "knowledge_base"]
        )
        self.register_template(
            "risk_assessment",
            RISK_ASSESSMENT_PROMPT,
            ["action", "user", "context"]
        )
    
    def register_template(
        self,
        name: str,
        template: str,
        variables: list[str],
    ):
        """Register prompt template."""
        self.templates[name] = PromptTemplate(name, template, variables)
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """Get prompt template by name."""
        return self.templates.get(name)
    
    def render_prompt(self, name: str, **kwargs) -> str:
        """Render prompt template."""
        template = self.get_template(name)
        if not template:
            raise ValueError(f"Template not found: {name}")
        
        return template.render(**kwargs)
    
    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return SYSTEM_PROMPT


# Global prompt manager instance
prompt_manager = PromptManager()
