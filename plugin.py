"""鹿管记录与月度统计插件。

群成员发送 🦌 时记录鹿管次数（带限频），支持：
- 排行榜查询（🦌王）
- 个人统计（我的鹿管）
- 月度图表（X月鹿表 / 上月鹿表 / 本月鹿表）
- LLM Tool 查询
- 历史总榜、连续打卡、时段分布、单日最高等趣味统计
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from maibot_sdk import Command, EventHandler, Field, MaiBotPlugin, PluginConfigBase, Tool

from . import chart_template
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType

# 插件目录与数据路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PLUGIN_DIR, "data")
CACHE_DIR = os.path.join(PLUGIN_DIR, "chart_cache")

# 时间段标签
HOUR_LABELS = ["凌晨(0-6)", "早上(6-9)", "上午(9-12)", "中午(12-14)", "下午(14-18)", "晚上(18-21)", "深夜(21-24)"]
_HOUR_BREAKPOINTS = [6, 9, 12, 14, 18, 21]

def _get_hour_label(hour: int) -> str:
    """根据小时数返回时段标签。"""
    index = bisect.bisect_right(_HOUR_BREAKPOINTS, hour)
    return HOUR_LABELS[index]


# ===== 配置模型 =====


class PluginSectionConfig(PluginConfigBase):
    """插件开关配置"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=False, description="是否启用插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class TriggerConfig(PluginConfigBase):
    """触发词配置：鹿管记录触发词 排行榜查询触发词 个人统计查询触发词 月度图表触发词后缀"""

    __ui_label__ = "触发词"
    __ui_icon__ = "zap"
    __ui_order__ = 1

    deer_pipe_record_words: str = Field(default="🦌", description="鹿管记录触发词")
    deer_pipe_rank_words: str = Field(default="鹿王", description="排行榜查询触发词")
    deer_pipe_personal_words: str = Field(default="我的鹿管", description="个人统计查询触发词")
    deer_pipe_monthly_words: str = Field(default="月鹿表", description="月度图表触发词后缀，如'6月鹿表'")


class RateLimitConfig(PluginConfigBase):
    """限频配置：每次记录的冷却时间（分钟） 超限时的回复内容"""

    __ui_label__ = "限频"
    __ui_icon__ = "clock"
    __ui_order__ = 2

    cooldown_minutes: int = Field(default=24, description="每次记录的冷却时间（分钟）")
    exceed_reply: str = Field(default="注意身体，歇会儿吧！", description="超限时的回复内容")


class RetentionConfig(PluginConfigBase):
    """数据保留配置：数据保留月数 是否在加载时自动清理过期数据"""

    __ui_label__ = "数据保留"
    __ui_icon__ = "archive"
    __ui_order__ = 3

    months: int = Field(default=2, description="数据保留月数")
    auto_cleanup: bool = Field(default=True, description="是否在加载时自动清理过期数据")


class GroupFilterConfig(PluginConfigBase):
    """群过滤配置（白名单模式）留空表示允许所有群"""

    __ui_label__ = "群过滤"
    __ui_icon__ = "users"
    __ui_order__ = 4

    allowed_groups: list[str] = Field(default_factory=list, description="白名单群号列表，留空表示允许所有群")


class DeerPluginConfig(PluginConfigBase):
    """鹿管插件总配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    group_filter: GroupFilterConfig = Field(default_factory=GroupFilterConfig)


def _parse_triggers(trigger_str: str) -> list[str]:
    """解析逗号分隔的触发词列表，去除空白和空项。"""
    return [t.strip() for t in trigger_str.split(",") if t.strip()]


def _get_first_trigger(trigger_str: str) -> str:
    """获取第一个触发词（用于提示消息中的软编码）。"""
    triggers = _parse_triggers(trigger_str)
    return triggers[0] if triggers else trigger_str

# ===== 鹿管插件主类 =====


class DeerPipeTablePlugin(MaiBotPlugin):
    """鹿管记录与月度统计插件。"""

    config_model = DeerPluginConfig

    # ===== 数据层 =====

    def _data_path(self, group_id: str, month_key: str) -> str:
        """获取指定群+月的数据文件路径。"""
        os.makedirs(DATA_DIR, exist_ok=True)
        safe_group = re.sub(r"[^\w\-]", "_", group_id)
        return os.path.join(DATA_DIR, f"{safe_group}_{month_key}.json")

    def _cache_path(self, group_id: str, month_key: str) -> str:
        """获取图表缓存文件路径。"""
        os.makedirs(CACHE_DIR, exist_ok=True)
        safe_group = re.sub(r"[^\w\-]", "_", group_id)
        return os.path.join(CACHE_DIR, f"{safe_group}_{month_key}.txt")

    def _load_records(self, group_id: str, month_key: str) -> list[dict]:
        """加载指定群+月的记录列表。"""
        path = self._data_path(group_id, month_key)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_records(self, group_id: str, month_key: str, records: list[dict]) -> None:
        """保存记录列表到文件。"""
        path = self._data_path(group_id, month_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _check_cooldown(self, group_id: str, user_id: str) -> tuple[bool, int]:
        """检查用户是否在冷却期内。返回 (是否在冷却中, 距离上次记录的秒数)。"""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        cooldown = timedelta(minutes=self.config.rate_limit.cooldown_minutes)

        records = self._load_records(group_id, month_key)
        last_ts = None
        for r in records:
            if r.get("user_id") != user_id:
                continue
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            except (ValueError, KeyError):
                continue

        if last_ts is None:
            return False, 0
        elapsed = (now - last_ts).total_seconds()
        return elapsed < cooldown.total_seconds(), int(elapsed)

    def _add_record(self, group_id: str, user_id: str, nickname: str) -> bool:
        """添加一条鹿管记录。返回 True 表示添加成功，False 表示在冷却期被拒绝。"""
        in_cooldown, _ = self._check_cooldown(group_id, user_id)
        if in_cooldown:
            return False

        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        records = self._load_records(group_id, month_key)

        # 更新已有用户的昵称
        for r in records:
            if r.get("user_id") == user_id:
                r["nickname"] = nickname

        records.append({
            "user_id": user_id,
            "nickname": nickname,
            "timestamp": now.strftime("%Y-%m-%dT%H:%M"),
        })
        self._save_records(group_id, month_key, records)

        # 清除图表缓存
        cache_path = self._cache_path(group_id, month_key)
        if os.path.exists(cache_path):
            os.remove(cache_path)

        return True

    def _get_monthly_stats(self, group_id: str, month_key: str) -> dict[str, dict]:
        """统计指定群+月各用户的鹿管数据。

        Returns:
            {user_id: {"nickname": str, "count": int, "days": set, "timestamps": list}}
        """
        records = self._load_records(group_id, month_key)
        stats: dict[str, dict] = {}
        for r in records:
            uid = r["user_id"]
            if uid not in stats:
                stats[uid] = {
                    "nickname": r["nickname"],
                    "count": 0,
                    "days": set(),
                    "timestamps": [],
                }
            stats[uid]["count"] += 1
            stats[uid]["nickname"] = r["nickname"]  # 使用最新昵称
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                stats[uid]["days"].add(ts.day)
            except ValueError:
                pass
            stats[uid]["timestamps"].append(r["timestamp"])
        return stats

    def _get_all_time_stats(self, group_id: str) -> dict[str, dict]:
        """统计指定群所有历史月份的鹿管数据。"""
        all_stats: dict[str, dict] = {}
        if not os.path.exists(DATA_DIR):
            return all_stats
        safe_group = re.sub(r"[^\w\-]", "_", group_id)
        pattern = re.compile(rf"^{re.escape(safe_group)}_(\d{{4}}-\d{{2}})\.json$")
        for filename in os.listdir(DATA_DIR):
            match = pattern.match(filename)
            if not match:
                continue
            month_key = match.group(1)
            month_stats = self._get_monthly_stats(group_id, month_key)
            for uid, data in month_stats.items():
                if uid not in all_stats:
                    all_stats[uid] = {"nickname": data["nickname"], "count": 0, "days": set()}
                all_stats[uid]["count"] += data["count"]
                all_stats[uid]["nickname"] = data["nickname"]
                all_stats[uid]["days"].update(data["days"])
        return all_stats

    def _get_streak(self, group_id: str, user_id: str) -> int:
        """计算用户在本月的最长连续打卡天数。"""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        records = self._load_records(group_id, month_key)
        user_days = set()
        for r in records:
            if r.get("user_id") != user_id:
                continue
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                user_days.add(ts.day)
            except ValueError:
                continue
        if not user_days:
            return 0
        sorted_days = sorted(user_days)
        max_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_days)):
            if sorted_days[i] == sorted_days[i - 1] + 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1
        return max_streak

    def _get_hourly_distribution(self, group_id: str, month_key: str) -> dict[str, int]:
        """统计指定群+月的时段分布。"""
        records = self._load_records(group_id, month_key)
        dist: dict[str, int] = {label: 0 for label in HOUR_LABELS}
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                label = _get_hour_label(ts.hour)
                dist[label] += 1
            except (ValueError, KeyError):
                continue
        return dist

    def _get_daily_max(self, group_id: str, month_key: str) -> tuple[str, int]:
        """获取单日最高记录。返回 (日期, 次数)。"""
        records = self._load_records(group_id, month_key)
        day_count: dict[str, int] = defaultdict(int)
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                day_count[ts.strftime("%m-%d")] += 1
            except (ValueError, KeyError):
                continue
        if not day_count:
            return "无", 0
        best_day = max(day_count, key=lambda k: day_count[k])
        return best_day, day_count[best_day]

    def _cleanup_old_records(self) -> None:
        """清理过期数据文件。"""
        if not self.config.retention.auto_cleanup:
            return
        if not os.path.exists(DATA_DIR):
            return
        cutoff = datetime.now() - timedelta(days=self.config.retention.months * 31)
        for filename in os.listdir(DATA_DIR):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(DATA_DIR, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
            except OSError:
                continue

    # ===== @Command — 统一消息路由器 =====

    @Command(
        "deer_message_router",
        description="统一消息路由器：按触发词分发到鹿管记录、排行榜或个人统计，支持逗号多匹配",
        pattern=r"^.+$",
    )
    async def handle_message_router(self, stream_id: str = "", **kwargs: Any) -> Any:
        """根据配置的触发词将消息路由到对应的处理器。"""

        if not stream_id:
            return False, "无法获取聊天流信息", 0

        raw_text = str(kwargs.get("text") or "").strip()
        if not raw_text:
            return False, "", 0

        # 提取用户信息（统一从 kwargs 获取）
        user_id = str(kwargs.get("user_id") or "")
        message_dict = kwargs.get("message") or {}
        nickname = str(
            (message_dict.get("message_info") or {}).get("user_info", {}).get("user_nickname", "")
        ) or (f"用户{user_id[-4:]}" if user_id else "未知")

        # 1. 鹿管记录触发词
        record_triggers = _parse_triggers(self.config.trigger.deer_pipe_record_words)
        if raw_text in record_triggers:
            return await self._route_deer_record(stream_id, user_id, nickname)

        # 2. 排行榜触发词
        rank_triggers = _parse_triggers(self.config.trigger.deer_pipe_rank_words)
        if raw_text in rank_triggers:
            return await self._route_deer_pipe_rank(stream_id)

        # 3. 个人统计触发词
        personal_triggers = _parse_triggers(self.config.trigger.deer_pipe_personal_words)
        if raw_text in personal_triggers:
            return await self._route_personal(stream_id, user_id, nickname)

        # 4. 月度图表触发词
        if raw_text == "上月鹿表":
            now = datetime.now()
            month_num = now.month - 1 if now.month > 1 else 12
            return await self._handle_monthly_chart(stream_id, month_num)
        if raw_text == "本月鹿表":
            return await self._handle_monthly_chart(stream_id, datetime.now().month)
        num_match = re.match(r"^(?P<m>\d{1,2})月鹿表$", raw_text)
        if num_match:
            return await self._handle_monthly_chart(stream_id, int(num_match.group("m")))

        return False, "", 0

    async def _route_deer_record(self, stream_id: str, user_id: str, nickname: str) -> Any:
        """鹿管记录子路由。"""
        if not user_id:
            self.ctx.logger.warning("鹿管记录：无法获取发送者 user_id，跳过记录")
            return False, "无法识别用户身份", 0

        # 白名单校验
        allowed = self.config.group_filter.allowed_groups
        if allowed and stream_id not in allowed:
            return True, "非白名单群，已忽略", 2

        success = self._add_record(stream_id, user_id, nickname)
        if not success:
            cooldown = self.config.rate_limit.cooldown_minutes
            await self.ctx.send.text(
                self.config.rate_limit.exceed_reply + f"（每{cooldown}分钟只能记录一次哦）", stream_id
            )
            return True, "冷却期内拦截", 2

        # 记录成功 → 个人热力图报告
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self._get_monthly_stats(stream_id, month_key)
        user_data = stats.get(user_id, {})
        user_count = user_data.get("count", 0)

        # 计算每日真实次数
        day_counts: dict[int, int] = {}
        for ts_str in user_data.get("timestamps", []):
            try:
                d = datetime.fromisoformat(ts_str).day
                day_counts[d] = day_counts.get(d, 0) + 1
            except ValueError:
                pass

        try:
            html = chart_template.build_personal_heatmap(month_key, nickname, user_count, day_counts)
            week_num = now.isocalendar()[1]
            result = await self.ctx.render.html2png(
                html=html,
                selector="#chart-container",
                viewport={"width": 620, "height": 520},
                device_scale_factor=2.0,
                full_page=True,
                wait_until="networkidle",
            )
            image_base64 = self._extract_base64(result)
            if image_base64:
                await self.ctx.send.text(f"记录成功！本月第{user_count}次 🦌", stream_id)
                await self.ctx.send.image(image_base64, stream_id)
            else:
                self.ctx.logger.warning(f"html2png 返回异常: type={type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                await self.ctx.send.text(f"记录成功！本月第{user_count}次 🦌", stream_id)
        except Exception:
            await self.ctx.send.text(f"记录成功！本月第{user_count}次 🦌", stream_id)

        return True, "鹿管已记录", 2

    async def _route_deer_pipe_rank(self, stream_id: str) -> Any:
        """排行榜子路由。"""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self._get_monthly_stats(stream_id, month_key)

        if not stats:
            first_trigger = _get_first_trigger(self.config.trigger.deer_pipe_record_words)
            await self.ctx.send.text(
                f"本月还没有鹿管记录哦～\n发送 {first_trigger} 来记录吧！", stream_id
            )
            return True, "本月无记录", 2

        sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
        total_count = sum(d["count"] for _, d in sorted_users)

        try:
            html = chart_template.build_deer_pipe_rank_chart(month_key, sorted_users, total_count)
            result = await self.ctx.render.html2png(
                html=html,
                selector="#chart-container",
                viewport={"width": 660, "height": 500},
                device_scale_factor=2.0,
                full_page=True,
                wait_until="networkidle",
            )
            image_base64 = self._extract_base64(result)
            if image_base64:
                await self.ctx.send.image(image_base64, stream_id)
                return True, "已发送排行榜图表", 2
        except Exception:
            pass

        # 降级为文本
        lines = [f"本月鹿管排行榜（{month_key}）", f"总次数：{total_count}", "─" * 20]
        for i, (uid, data) in enumerate(sorted_users[:10], 1):
            medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {data['nickname']}：{data['count']} 次")
        await self.ctx.send.text("\n".join(lines), stream_id)
        return True, "已发送排行榜", 2

    async def _route_personal(self, stream_id: str, user_id: str, nickname: str) -> Any:
        """个人统计子路由。"""
        if not user_id:
            return False, "无法识别用户身份", 0
        await self._handle_personal_stats(stream_id, user_id, nickname)
        return True, "已发送个人统计", 2

    # ===== 个人统计（核心逻辑） =====
    # ===== 个人统计（内部方法，由 EventHandler 路由调用） =====

    async def _handle_personal_stats(self, stream_id: str, user_id: str, nickname: str) -> None:
        """处理个人统计查询，生成热力图图片发送。"""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self._get_monthly_stats(stream_id, month_key)

        user_data = stats.get(user_id)
        if not user_data:
            first_trigger = _get_first_trigger(self.config.trigger.deer_pipe_record_words)
            await self.ctx.send.text(
                f"{nickname or '你'} 本月还没有鹿管记录哦～\n发送 {first_trigger} 来记录吧！", stream_id
            )
            return

        user_count = user_data.get("count", 0)
        day_counts: dict[int, int] = {}
        for ts_str in user_data.get("timestamps", []):
            try:
                d = datetime.fromisoformat(ts_str).day
                day_counts[d] = day_counts.get(d, 0) + 1
            except ValueError:
                pass

        try:
            html = chart_template.build_personal_heatmap(month_key, nickname, user_count, day_counts)
            result = await self.ctx.render.html2png(
                html=html,
                selector="#chart-container",
                viewport={"width": 620, "height": 520},
                device_scale_factor=2.0,
                full_page=True,
                wait_until="networkidle",
            )
            image_base64 = self._extract_base64(result)
            if image_base64:
                await self.ctx.send.image(image_base64, stream_id)
        except Exception:
            pass

    async def _handle_monthly_chart(self, stream_id: str, month_num: int) -> Any:
        """统一处理月度图表生成与发送。"""
        if not stream_id:
            return False, "无法获取聊天流信息", 0

        if month_num < 1 or month_num > 12:
            await self.ctx.send.text("月份不合法，请输入 1-12 之间的数字～", stream_id)
            return False, "月份不合法", 0

        now = datetime.now()
        # 推断年份：若查询月份大于当前月份，则为上一年
        year = now.year if month_num <= now.month else now.year - 1
        month_key = f"{year}-{month_num:02d}"

        stats = self._get_monthly_stats(stream_id, month_key)
        if not stats:
            await self.ctx.send.text(f"📊 {month_key} 还没有鹿管记录哦～", stream_id)
            return True, "指定月份无记录", 2

        # 生成图表
        image_base64 = await self._generate_full_report(stream_id, month_key, stats)
        if image_base64:
            await self.ctx.send.image(image_base64, stream_id)
            return True, f"已发送 {month_key} 鹿管月表", 2

        # 图表生成失败时发送文本统计
        sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
        total = sum(d["count"] for _, d in sorted_users)
        lines = [f"📊 {month_key} 鹿管月表", f"🦌 总次数：{total}", "─" * 20]
        for i, (uid, data) in enumerate(sorted_users[:10], 1):
            lines.append(f"{i}. {data['nickname']}：{data['count']} 次")
        await self.ctx.send.text("\n".join(lines), stream_id)
        return True, f"已发送 {month_key} 文本统计", 2

    # ===== @Tool — LLM 工具 =====

    @Tool(
        "deer_pipe_rank",
        description="查询本群本月鹿管次数排行榜。当用户询问'谁最鹿'、'鹿管排名'、'排行榜'时使用此工具。"
        "返回 Top 10 排名及各自鹿管次数。",
        parameters=[
            ToolParameterInfo(
                name="stream_id",
                param_type=ToolParamType.STRING,
                description="当前聊天流 ID",
                required=True,
            ),
        ],
    )
    async def tool_query_deer_pipe_rank(self, stream_id: str = "", **kwargs: Any) -> dict:
        """LLM Tool：查询鹿管排行榜。"""
        del kwargs
        try:
            now = datetime.now()
            month_key = now.strftime("%Y-%m")
            stats = self._get_monthly_stats(stream_id, month_key)
            if not stats:
                return {"name": "deer_pipe_rank", "content": "本月暂无鹿管记录。"}

            sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
            lines = [f"🏆 {month_key} 鹿管排行榜："]
            for i, (uid, data) in enumerate(sorted_users[:10], 1):
                lines.append(f"{i}. {data['nickname']}：{data['count']} 次")
            return {"name": "deer_pipe_rank", "content": "\n".join(lines)}
        except Exception as e:
            return {"name": "deer_pipe_rank", "content": f"查询排行榜失败：{e}"}

    @Tool(
        "deer_pipe_monthly",
        description="查询指定月份的鹿管统计数据和趣味分析。当用户询问'X月鹿表'、'月度统计'、'这个月鹿管情况'时使用。"
        "返回月度总次数、Top 排行、热门时段、单日最高和连续打卡王等信息。",
        parameters=[
            ToolParameterInfo(
                name="stream_id",
                param_type=ToolParamType.STRING,
                description="当前聊天流 ID",
                required=True,
            ),
            ToolParameterInfo(
                name="month",
                param_type=ToolParamType.INTEGER,
                description="查询月份（1-12），默认为当前月",
                required=False,
            ),
        ],
    )
    async def tool_query_monthly(self, stream_id: str = "", month: int = 0, **kwargs: Any) -> dict:
        """LLM Tool：查询月度鹿管统计。"""
        del kwargs
        try:
            now = datetime.now()
            if month < 1 or month > 12:
                month = now.month
            year = now.year if month <= now.month else now.year - 1
            month_key = f"{year}-{month:02d}"

            stats = self._get_monthly_stats(stream_id, month_key)
            if not stats:
                return {"name": "deer_pipe_monthly", "content": f"{month_key} 暂无鹿管记录。"}

            sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
            total = sum(d["count"] for _, d in sorted_users)
            hourly = self._get_hourly_distribution(stream_id, month_key)
            peak_hour = max(hourly, key=lambda k: hourly[k])
            best_day, best_count = self._get_daily_max(stream_id, month_key)

            # 连续打卡王
            max_streak_user = ""
            max_streak = 0
            for uid in stats:
                s = self._get_streak(stream_id, uid)
                if s > max_streak:
                    max_streak = s
                    max_streak_user = stats[uid]["nickname"]

            lines = [
                f"📊 {month_key} 鹿管月表",
                f"🦌 总鹿管次数：{total}",
                f"👑 鹿管王：{sorted_users[0][1]['nickname']}（{sorted_users[0][1]['count']} 次）",
                f"🔥 连续打卡王：{max_streak_user}（{max_streak} 天）",
                f"⏰ 最活跃时段：{peak_hour}（{hourly[peak_hour]} 次）",
                f"📅 单日最高：{best_day}（{best_count} 次）",
            ]
            return {"name": "deer_pipe_monthly", "content": "\n".join(lines)}
        except Exception as e:
            return {"name": "deer_pipe_monthly", "content": f"查询月表失败：{e}"}

    @Tool(
        "deer_pipe_personal",
        description="查询指定群成员的鹿管个人统计。当用户询问'我鹿了多少次'、'我的鹿管排名'、'XX的鹿管统计'时使用。"
        "返回该成员的鹿管次数、群内排名、活跃天数、最长连续打卡和时段偏好。",
        parameters=[
            ToolParameterInfo(
                name="stream_id",
                param_type=ToolParamType.STRING,
                description="当前聊天流 ID",
                required=True,
            ),
            ToolParameterInfo(
                name="user_id",
                param_type=ToolParamType.STRING,
                description="要查询的用户 ID（QQ号），不传则默认查询发送者本人",
                required=False,
            ),
            ToolParameterInfo(
                name="nickname",
                param_type=ToolParamType.STRING,
                description="要查询的用户昵称（用于展示）",
                required=False,
            ),
        ],
    )
    async def tool_query_personal(
        self, stream_id: str = "", user_id: str = "", nickname: str = "", **kwargs: Any
    ) -> dict:
        """LLM Tool：查询个人鹿管统计。"""
        del kwargs
        try:
            if not user_id:
                return {"name": "deer_pipe_personal", "content": "请指定要查询的用户 ID。"}

            now = datetime.now()
            month_key = now.strftime("%Y-%m")
            stats = self._get_monthly_stats(stream_id, month_key)
            user_data = stats.get(user_id)

            if not user_data:
                display_name = nickname or user_id
                return {"name": "deer_pipe_personal", "content": f"{display_name} 本月暂无鹿管记录。"}

            sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
            rank = next(i for i, (uid, _) in enumerate(sorted_users, 1) if uid == user_id)
            streak = self._get_streak(stream_id, user_id)

            lines = [
                f"📊 {user_data['nickname']} 本月鹿管统计",
                f"🦌 鹿管次数：{user_data['count']} 次",
                f"🏅 排名：第 {rank} 名（共 {len(stats)} 人）",
                f"🔥 最长连续打卡：{streak} 天",
                f"📅 活跃天数：{len(user_data['days'])} 天",
            ]
            return {"name": "deer_pipe_personal", "content": "\n".join(lines)}
        except Exception as e:
            return {"name": "deer_pipe_personal", "content": f"查询个人统计失败：{e}"}


    # ===== 图表生成 =====

    @staticmethod
    def _extract_base64(result: Any) -> str | None:
        """从 html2png 返回结果中提取 image_base64，兼容两种 SDK 格式。"""
        if not isinstance(result, dict):
            return None
        # 格式1: {"image_base64": "...", ...}
        if result.get("image_base64"):
            return result["image_base64"]
        # 格式2: {"success": True, "result": {"image_base64": "...", ...}}
        inner = result.get("result")
        if isinstance(inner, dict) and inner.get("image_base64"):
            return inner["image_base64"]
        return None

    async def _generate_full_report(self, group_id: str, month_key: str, stats: dict) -> str | None:
        """生成月度完整报告图片，返回 base64 字符串。

        先检查缓存，命中则直接返回；否则调用 chart_template 渲染并缓存。
        """
        cache_path = self._cache_path(group_id, month_key)
        records = self._load_records(group_id, month_key)
        data_hash = hashlib.md5(json.dumps(records, sort_keys=True).encode()).hexdigest()

        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = f.read().strip()
                parts = cached.split(":", 1)
                if len(parts) == 2 and parts[0] == data_hash:
                    return parts[1]
            except OSError:
                pass

        try:
            hourly = self._get_hourly_distribution(group_id, month_key)
            best_day = self._get_daily_max(group_id, month_key)
            streak_king_name = "暂无"
            streak_king_count = 0
            for uid in stats:
                s = self._get_streak(group_id, uid)
                if s > streak_king_count:
                    streak_king_count = s
                    streak_king_name = stats[uid]["nickname"]
            all_time = self._get_all_time_stats(group_id)
            all_time_sorted = sorted(all_time.items(), key=lambda x: x[1]["count"], reverse=True)

            html = chart_template.build_full_report(
                month_key, stats, group_id, hourly, best_day,
                streak_king_name, streak_king_count, all_time_sorted,
            )
            result = await self.ctx.render.html2png(
                html=html,
                selector="#chart-container",
                viewport={"width": 820, "height": 900},
                device_scale_factor=2.0,
                full_page=True,
                wait_until="networkidle",
            )
            image_base64 = self._extract_base64(result)
            if image_base64:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(f"{data_hash}:{image_base64}")
                return image_base64
            return None
        except Exception:
            return None

    # ===== 生命周期 =====

    async def on_load(self) -> None:
        """插件加载时初始化数据目录并清理过期记录。"""
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._cleanup_old_records()
        self.ctx.logger.info("鹿管插件已加载")

    async def on_unload(self) -> None:
        """插件卸载时清理资源。"""
        self.ctx.logger.info("鹿管插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """处理配置热重载事件。

        Args:
            scope: 配置变更范围（"self" / "bot" / "model"）。
            config_data: 最新配置数据。
            version: 配置版本号。
        """
        del config_data, version
        if scope == "self":
            self.ctx.logger.info("鹿管插件配置已更新")


def create_plugin() -> DeerPipeTablePlugin:
    """创建鹿管插件实例。

    Returns:
        DeerPipeTablePlugin: 插件实例。
    """
    return DeerPipeTablePlugin()
