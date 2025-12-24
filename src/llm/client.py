"""
LLM Client Module
Provides unified interface for different LLM providers
"""
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseLLMClient(ABC):
    """Base class for LLM clients"""
    
    @abstractmethod
    async def generate(self,
                      system_prompt: str,
                      user_message: str,
                      response_format: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.7) -> str:
        """Generate a response from the LLM"""
        pass
    
    @abstractmethod
    async def generate_with_tools(self,
                                  system_prompt: str,
                                  messages: List[Dict[str, str]],
                                  tools: List[Dict[str, Any]],
                                  temperature: float = 0.7) -> Dict[str, Any]:
        """Generate a response with potential tool calls"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API client"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client
    
    async def generate(self,
                      system_prompt: str,
                      user_message: str,
                      response_format: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.7) -> str:
        """Generate a response using OpenAI"""
        client = self._get_client()
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        
        create: Any = client.chat.completions.create
        response: Any = await create(**kwargs)
        
        return response.choices[0].message.content
    
    async def generate_with_tools(self,
                                  system_prompt: str,
                                  messages: List[Dict[str, str]],
                                  tools: List[Dict[str, Any]],
                                  temperature: float = 0.7) -> Dict[str, Any]:
        """Generate a response with tool calling"""
        client = self._get_client()
        
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]
        
        create: Any = client.chat.completions.create
        response: Any = await create(
            model=self.model,
            messages=full_messages,
            tools=tools,
            temperature=temperature
        )
        
        message = response.choices[0].message
        
        result = {
            "content": message.content,
            "tool_calls": []
        }
        
        if getattr(message, "tool_calls", None):
            for tool_call in message.tool_calls:
                function = getattr(tool_call, "function", None)
                if function is None:
                    continue

                name = getattr(function, "name", None)
                arguments_raw = getattr(function, "arguments", "{}")
                if not isinstance(name, str) or not name:
                    continue

                try:
                    arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else (arguments_raw or {})
                except Exception:
                    arguments = {}

                result["tool_calls"].append({
                    "id": getattr(tool_call, "id", ""),
                    "name": name,
                    "arguments": arguments
                })
        
        return result


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client
    
    async def generate(self,
                      system_prompt: str,
                      user_message: str,
                      response_format: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.7) -> str:
        """Generate a response using Claude"""
        client = self._get_client()
        
        # Add JSON instruction if needed
        if response_format and response_format.get("type") == "json_object":
            system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON, no other text."
        
        create: Any = client.messages.create
        response: Any = await create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ],
            temperature=temperature
        )

        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text" and hasattr(block, "text"):
                return block.text

        # Fallback: stringify if the SDK returns an unexpected structure
        return str(response)
    
    async def generate_with_tools(self,
                                  system_prompt: str,
                                  messages: List[Dict[str, str]],
                                  tools: List[Dict[str, Any]],
                                  temperature: float = 0.7) -> Dict[str, Any]:
        """Generate a response with tool calling"""
        client = self._get_client()
        
        # Convert tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func["description"],
                    "input_schema": func["parameters"]
                })
        
        create: Any = client.messages.create
        response: Any = await create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=anthropic_tools,
            temperature=temperature
        )
        
        result = {
            "content": None,
            "tool_calls": []
        }
        
        for block in response.content:
            if block.type == "text":
                result["content"] = block.text
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })
        
        return result


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for testing without API calls
    Returns predefined responses in Marathi
    """
    
    def __init__(self):
        self.call_count = 0
        self.last_prompt = None
    
    async def generate(self,
                      system_prompt: str,
                      user_message: str,
                      response_format: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.7) -> str:
        """Generate a mock response"""
        self.call_count += 1
        self.last_prompt = user_message
        
        # Return JSON for planning/evaluation prompts
        if response_format and response_format.get("type") == "json_object":
            if "योजना" in system_prompt or "plan" in system_prompt.lower():
                return json.dumps({
                    "goal": "सरकारी योजना शोधणे",
                    "reasoning": "वापरकर्त्याला योग्य योजना शोधण्यात मदत करणे आवश्यक आहे",
                    "tasks": [
                        {
                            "id": "task_1",
                            "description": "वापरकर्त्याची माहिती गोळा करा",
                            "tool_name": "eligibility_checker",
                            "tool_params": {},
                            "dependencies": []
                        },
                        {
                            "id": "task_2",
                            "description": "योजना शोधा",
                            "tool_name": "scheme_retriever",
                            "tool_params": {"query": user_message},
                            "dependencies": ["task_1"]
                        }
                    ],
                    "missing_info": ["age", "income"],
                    "clarifying_questions": ["तुमचे वय किती आहे?", "तुमचे वार्षिक उत्पन्न किती आहे?"]
                }, ensure_ascii=False)
            
            elif "मूल्यांकन" in system_prompt or "evaluat" in system_prompt.lower():
                return json.dumps({
                    "success": True,
                    "confidence": 0.85,
                    "needs_replanning": False,
                    "missing_information": [],
                    "contradictions": [],
                    "suggestions": [],
                    "next_action": "respond_to_user",
                    "user_response": "तुम्ही पीएम किसान योजनेसाठी पात्र आहात."
                }, ensure_ascii=False)
            
            elif "extract" in system_prompt.lower() or "काढा" in system_prompt:
                return json.dumps({
                    "age": None,
                    "income": None,
                    "occupation": "शेतकरी" if "शेतकरी" in user_message else None,
                    "intent": "scheme_search"
                }, ensure_ascii=False)
            
            else:
                return json.dumps({
                    "response": "मी तुम्हाला सरकारी योजनांबद्दल मदत करतो. कृपया तुमची माहिती सांगा.",
                    "eligible_schemes": [],
                    "next_steps": ["प्रथम तुमचे वय सांगा", "तुमचे उत्पन्न सांगा"]
                }, ensure_ascii=False)
        
        # Return text response
        return "नमस्कार! मी तुमचा सरकारी योजना सहाय्यक आहे. मी तुम्हाला योग्य योजना शोधण्यात आणि अर्ज करण्यात मदत करतो. कृपया तुमची माहिती सांगा."
    
    async def generate_with_tools(self,
                                  system_prompt: str,
                                  messages: List[Dict[str, str]],
                                  tools: List[Dict[str, Any]],
                                  temperature: float = 0.7) -> Dict[str, Any]:
        """Generate mock response with tool calls"""
        self.call_count += 1
        
        return {
            "content": "मी तुमची पात्रता तपासत आहे...",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "eligibility_checker",
                    "arguments": {
                        "occupation": "farmer"
                    }
                }
            ]
        }


class OllamaClient(BaseLLMClient):
    """
    Ollama client for free local LLM inference.
    Requires Ollama to be installed and running locally.
    Install: https://ollama.ai/download
    Then run: ollama pull llama3.2
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip('/')
        self.model = model
    
    async def generate(self,
                      system_prompt: str,
                      user_message: str,
                      response_format: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.7) -> str:
        """Generate a response using Ollama"""
        import aiohttp
        
        # Build the prompt
        prompt = f"{system_prompt}\n\nUser: {user_message}\nAssistant:"
        
        # Add JSON instruction if needed
        if response_format and response_format.get("type") == "json_object":
            prompt += " (Respond ONLY with valid JSON, no other text)"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        # If JSON format requested, set format
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama error: {error_text}")
                
                result = await response.json()
                return result.get("response", "")
    
    async def generate_with_tools(self,
                                  system_prompt: str,
                                  messages: List[Dict[str, str]],
                                  tools: List[Dict[str, Any]],
                                  temperature: float = 0.7) -> Dict[str, Any]:
        """
        Generate a response with tool calling.
        Ollama doesn't natively support tools, so we simulate it via prompting.
        """
        import aiohttp
        
        # Build tool descriptions
        tool_desc = "Available tools:\n"
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                tool_desc += f"- {func['name']}: {func['description']}\n"
                tool_desc += f"  Parameters: {json.dumps(func['parameters'], indent=2)}\n\n"
        
        # Build conversation
        conversation = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            conversation += f"{role.capitalize()}: {content}\n"
        
        # Build prompt asking for tool selection
        prompt = f"""{system_prompt}

{tool_desc}

Conversation:
{conversation}

Based on the user's request, decide if you need to use a tool. 
If yes, respond with JSON in this exact format:
{{
    "use_tool": true,
    "tool_name": "<tool_name>",
    "tool_arguments": {{...}},
    "message": "<brief message to user>"
}}

If no tool is needed, respond with:
{{
    "use_tool": false,
    "message": "<your response to the user>"
}}

Respond with valid JSON only:"""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama error: {error_text}")
                
                result = await response.json()
                response_text = result.get("response", "{}")
        
        try:
            parsed = json.loads(response_text)
            
            tool_calls = []
            if parsed.get("use_tool", False):
                tool_calls.append({
                    "id": f"call_{hash(parsed.get('tool_name', '')) % 10000}",
                    "name": parsed.get("tool_name", ""),
                    "arguments": parsed.get("tool_arguments", {})
                })
            
            return {
                "content": parsed.get("message", ""),
                "tool_calls": tool_calls
            }
        except json.JSONDecodeError:
            return {
                "content": response_text,
                "tool_calls": []
            }
    
    async def check_available(self) -> bool:
        """Check if Ollama is running and the model is available"""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                        return self.model.split(":")[0] in models
            return False
        except:
            return False


class LLMClientFactory:
    """Factory for creating LLM clients"""
    
    @staticmethod
    def create(provider: str = "ollama", **kwargs) -> BaseLLMClient:
        """Create an LLM client based on provider"""
        providers = {
            "openai": OpenAIClient,
            "anthropic": AnthropicClient,
            "ollama": OllamaClient,
            "mock": MockLLMClient
        }
        
        if provider not in providers:
            raise ValueError(f"Unknown LLM provider: {provider}")
        
        return providers[provider](**kwargs)
    
    @staticmethod
    def create_from_settings() -> BaseLLMClient:
        """Create LLM client from environment settings - prioritizes free local Ollama"""
        from ..config import settings
        
        # Try Ollama first (free, local)
        ollama_client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model
        )
        print(f"Using Ollama with model: {settings.ollama_model}")
        print(f"Make sure Ollama is running: ollama serve")
        print(f"And model is pulled: ollama pull {settings.ollama_model}")
        return ollama_client
