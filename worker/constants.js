// #下面代码实现的功能：集中定义 Worker 常量
export const HISTORY_LIMIT = 20;
export const SESSION_COOKIE_NAME = "xiaomo_session";
export const CSRF_COOKIE_NAME = "xiaomo_csrf";
export const ADMIN_COOKIE_NAME = "xiaomo_admin";
export const DEFAULT_SESSION_HOURS = 24 * 7;
export const LOGIN_RATE_LIMIT_PER_MIN = 30;
export const LOGIN_LOCK_FAIL_THRESHOLD = 10;
export const LOGIN_LOCK_MINUTES = 10;
export const ADMIN_USERNAME = "Tong";
export const ADMIN_PASSWORD = "15010190";

// #下面代码实现的功能：定义系统提示词
export const SYSTEM_PROMPT = `你叫小墨，是一位温柔、真诚、可靠的陪伴者。
你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。
对话风格要求：
1) 共情优先，先接住情绪，再给建议。
2) 多用温和短句，不说教，不评判，不施压。
3) 适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。
4) 如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。
5) 遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。
始终用中文回复，保持温暖、陪伴感和边界感。`;
