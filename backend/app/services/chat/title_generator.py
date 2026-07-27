"""Smart title generation for chat sessions.

使用 LLM 基于对话内容生成简洁、准确的标题。
"""

from __future__ import annotations

from typing import List, Dict


def generate_title_prompt(messages: List[Dict[str, str]], max_messages: int = 3) -> str:
    """构建标题生成的 prompt。
    
    Args:
        messages: 对话消息列表
        max_messages: 最多使用前 N 条消息生成标题
    
    Returns:
        标题生成 prompt
    """
    # 只使用前几轮对话
    recent = messages[:max_messages * 2]  # user + assistant 成对
    
    conversation_text = []
    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")[:200]  # 截取前 200 字符
        
        if role == "user":
            conversation_text.append(f"用户: {content}")
        elif role == "assistant":
            conversation_text.append(f"AI: {content}")
    
    context = "\n".join(conversation_text)
    
    return f"""请为以下对话生成一个简洁、准确的标题（不超过 20 个字）。

对话内容：
{context}

要求：
1. 标题应准确概括对话主题
2. 使用用户的核心关键词
3. 不超过 20 个字
4. 不要使用引号或标点符号
5. 直接返回标题文本，不要其他内容

标题："""


async def generate_chat_title(
    messages: List[Dict[str, str]],
    provider_name: str = "deepseek",
) -> str:
    """使用 LLM 生成对话标题。
    
    Args:
        messages: 对话消息列表
        provider_name: LLM provider 名称
    
    Returns:
        生成的标题（如果失败，返回基于首条消息的简单标题）
    """
    from app.services.knowledge.provider_registry import ProviderRegistry
    
    if not messages:
        return "新对话"
    
    # 至少要有一条用户消息
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return "新对话"
    
    # 如果只有一条消息，直接使用前 20 字
    if len(messages) == 1:
        first_content = messages[0].get("content", "")[:20].strip()
        return first_content if first_content else "新对话"
    
    try:
        # 构建 prompt
        prompt = generate_title_prompt(messages)
        
        # 调用 LLM
        provider = ProviderRegistry().get_provider(provider_name)
        title = provider.chat([{"role": "user", "content": prompt}])
        
        # 清理标题
        title = title.strip().replace('"', '').replace("'", '').replace('：', '').replace(':', '')
        
        # 限制长度
        if len(title) > 30:
            title = title[:30]
        
        # 如果生成失败，回退到简单截取
        if not title or len(title) < 3:
            first_user = user_messages[0].get("content", "")[:20].strip()
            return first_user if first_user else "新对话"
        
        return title
        
    except Exception as e:
        # 失败回退：使用第一条用户消息的前 20 字
        first_user = user_messages[0].get("content", "")[:20].strip()
        return first_user if first_user else "新对话"


def should_generate_title(session_title: str | None, message_count: int) -> bool:
    """判断是否需要生成标题。
    
    Args:
        session_title: 当前会话标题
        message_count: 消息数量
    
    Returns:
        是否需要生成标题
    """
    # 已有标题且不是默认标题，不需要重新生成
    if session_title and session_title not in ("新对话", ""):
        return False
    
    # 至少有 2 条消息（一轮对话）再生成标题
    return message_count >= 2
