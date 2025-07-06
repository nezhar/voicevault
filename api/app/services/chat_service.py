from typing import List, Dict, Optional
from groq import Groq
from loguru import logger

from app.core.config import settings
from app.models.entry import Entry

class ChatService:
    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for chat service")
        
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"  # Llama 3.3 model for chat
    
    async def chat_with_entry(
        self, 
        entry: Entry, 
        user_message: str, 
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generate a chat response about an entry using Groq Llama 3.1
        
        Args:
            entry: The entry to chat about
            user_message: The user's message/question
            conversation_history: Previous messages in the conversation
            
        Returns:
            AI response as string
        """
        
        if not entry.transcript:
            raise ValueError("Entry must have a transcript to chat about")
        
        # Build conversation context
        messages = self._build_conversation_context(entry, user_message, conversation_history)
        
        try:
            # Call Groq API with Llama 3.1
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
                top_p=0.9,
                stream=False
            )
            
            response = completion.choices[0].message.content
            logger.info(f"Generated chat response for entry {entry.id} ({len(response)} chars)")
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating chat response: {str(e)}")
            raise Exception(f"Failed to generate chat response: {str(e)}")
    
    def _build_conversation_context(
        self, 
        entry: Entry, 
        user_message: str, 
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """Build the conversation context for the Llama model"""
        
        # System prompt with transcript context
        system_prompt = f"""You are an AI assistant helping users analyze and discuss voice transcripts. You have access to a transcript from "{entry.title}".

TRANSCRIPT CONTENT:
{entry.transcript}

Your role:
- Answer questions about the transcript content
- Provide insights, summaries, and analysis
- Help identify key points, action items, and important information
- Be conversational and helpful
- If asked about something not in the transcript, politely mention the limitation
- Keep responses focused and relevant to the audio content

Guidelines:
- Be accurate and only reference information from the provided transcript
- Provide specific quotes when relevant
- Help with analysis like sentiment, key themes, action items, etc.
- Be concise but thorough in your responses
"""

        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
        
        # Add current user message
        messages.append({
            "role": "user", 
            "content": user_message
        })
        
        return messages
    
    async def generate_summary(self, entry: Entry) -> str:
        """Generate a summary of the entry transcript"""
        
        if not entry.transcript:
            raise ValueError("Entry must have a transcript to summarize")
        
        summary_prompt = f"""Please provide a concise summary of this transcript from "{entry.title}":

TRANSCRIPT:
{entry.transcript}

Please provide:
1. A brief overview of the main topic/purpose
2. Key points discussed
3. Any action items or next steps mentioned
4. Overall outcome or conclusion

Keep the summary clear and structured."""

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at summarizing voice transcripts. Provide clear, structured summaries."},
                    {"role": "user", "content": summary_prompt}
                ],
                max_tokens=512,
                temperature=0.3,
                top_p=0.9
            )
            
            summary = completion.choices[0].message.content
            logger.info(f"Generated summary for entry {entry.id}")
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")
    
    def health_check(self) -> bool:
        """Check if Groq API is accessible for chat"""
        try:
            # Simple test call
            test_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            return bool(test_completion.choices[0].message.content)
        except Exception as e:
            logger.error(f"Chat service health check failed: {str(e)}")
            return False