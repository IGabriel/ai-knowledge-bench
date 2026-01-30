"""vLLM client wrapper with OpenAI-compatible interface."""
from typing import Iterator, Optional, Dict, Any, List
import json

import requests
from openai import OpenAI

from packages.core.config import get_settings
from packages.core.logging_config import setup_logging

logger = setup_logging(__name__)


class VLLMClient:
    """Client for vLLM with OpenAI-compatible API."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize vLLM client.
        
        Args:
            base_url: vLLM server base URL
            api_key: API key (usually 'EMPTY' for vLLM)
            model: Model name
        """
        settings = get_settings()
        self.base_url = base_url or settings.vllm_base_url
        self.api_key = api_key or settings.vllm_api_key
        self.model = model or settings.vllm_model
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        logger.info(f"vLLM client initialized: {self.base_url}, model: {self.model}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """
        Generate completion (non-streaming).
        
        Args:
            prompt: Prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Whether to stream (for this method, should be False)
            
        Returns:
            Generated text
        """
        try:
            response = self.client.completions.create(
                model=self.model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )
            
            return response.choices[0].text
        
        except Exception as e:
            logger.error(f"Error generating completion: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """
        Generate chat completion (non-streaming).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Whether to stream
            
        Returns:
            Generated text
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Error generating chat completion: {e}")
            raise
    
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> Iterator[str]:
        """
        Generate chat completion with streaming.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Yields:
            Text chunks as they are generated
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as e:
            logger.error(f"Error streaming chat completion: {e}")
            raise


def build_rag_prompt(query: str, context: str) -> List[Dict[str, str]]:
    """
    Build RAG prompt with context and query.
    
    Args:
        query: User query
        context: Retrieved context
        
    Returns:
        List of messages for chat API
    """
    system_message = """You are a helpful assistant that answers questions based on provided context.
Your answers must be grounded in the context provided. If the context doesn't contain enough information to answer the question, say so.
Always cite your sources using the [Source N] references provided in the context."""
    
    user_message = f"""Context:
{context}

Question: {query}

Please answer the question based on the context above. Cite your sources using [Source N] notation."""
    
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]


# Singleton instance
_vllm_client: Optional[VLLMClient] = None


def get_vllm_client() -> VLLMClient:
    """Get or create singleton vLLM client."""
    global _vllm_client
    if _vllm_client is None:
        _vllm_client = VLLMClient()
    return _vllm_client
