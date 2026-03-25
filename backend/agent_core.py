"""
这个文件实现什么功能：集中管理 VPS 侧主 agent 核心配置与消息组装。
它负责什么：提供人格层/安全层/场景层/定制层/版本层配置，以及统一的 system message 构建入口。
它不负责什么：不处理 HTTP 路由、鉴权、数据库、上游 API 调用。
对外暴露什么：AGENT_CORE_VERSION、AGENT_CORE_LAYERS、build_system_prompt、build_agent_messages。
依赖哪些关键模块：无（纯配置 + 纯函数）。
"""

#下面代码实现的功能：定义主 agent 核心版本，后续可用于灰度/回滚/评测对照
AGENT_CORE_VERSION = "v1"

#下面代码实现的功能：集中定义主 agent 各层文案，避免散落在路由或请求处理逻辑里
AGENT_CORE_LAYERS = {
    "persona": [
        "你叫小墨，是一位温柔、真诚、可靠的陪伴者。",
        "你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。",
    ],
    "style": [
        "共情优先，先接住情绪，再给建议。",
        "多用温和短句，不说教，不评判，不施压。",
        "适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。",
    ],
    "safety": [
        "如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。",
        "遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。",
    ],
    "output": ["始终用中文回复，保持温暖、陪伴感和边界感。"],
    "customization": [],
}


#下面代码实现的功能：把结构化层配置转成 system prompt 字符串

def build_system_prompt(extra_customization=None):
    normalized_customization = []
    for line in (extra_customization or []):
        if isinstance(line, str) and line.strip():
            normalized_customization.append(line.strip())

    sections = [
        *AGENT_CORE_LAYERS["persona"],
        "对话风格要求：",
        *[f"{index + 1}) {line}" for index, line in enumerate(AGENT_CORE_LAYERS["style"])],
        *[f"{index + 4}) {line}" for index, line in enumerate(AGENT_CORE_LAYERS["safety"])],
        *AGENT_CORE_LAYERS["output"],
        *AGENT_CORE_LAYERS["customization"],
        *normalized_customization,
    ]
    return "\n".join(sections)


#下面代码实现的功能：统一组装对话 messages，确保后端聊天逻辑只依赖这个入口

def build_agent_messages(user_message: str, history, customization=None):
    return [
        {"role": "system", "content": build_system_prompt(customization)},
        *(history if isinstance(history, list) else []),
        {"role": "user", "content": user_message},
    ]
