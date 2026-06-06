"""鹿管记录与月度统计插件。

群成员发送鹿管 emoji 时记录次数（带限频），支持：
- 鹿管记录 — 发送触发词记录一次并返回个人热力图
- 排行榜查询 — 查看本月鹿管王 Top 10
- 个人统计 — 查看个人月度热力图与统计
- 月度图表 — 生成含热力图/柱状图/趣味统计的完整报告
- 趣味统计 — 连续打卡王、单日最高、最活跃时段、历史总榜
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

from maibot_sdk import MaiBotPlugin
from maibot_sdk.compat.base.base_command import BaseCommand

from . import chart_template
from .config import CONFIG_SCHEMA_VERSION, DeerPluginConfig

# ═══════════════════════════════════════════════════════════════════════
# 路径与常量
# ═══════════════════════════════════════════════════════════════════════

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PLUGIN_DIR, "data")
CACHE_DIR = os.path.join(PLUGIN_DIR, "chart_cache")

HOUR_LABELS = ["凌晨(0-6)", "早上(6-9)", "上午(9-12)", "中午(12-14)", "下午(14-18)", "晚上(18-21)", "深夜(21-24)"]
_HOUR_BREAKPOINTS = [6, 9, 12, 14, 18, 21]


def _get_hour_label(hour: int) -> str:
    """根据小时数返回时段标签。"""
    index = bisect.bisect_right(_HOUR_BREAKPOINTS, hour)
    return HOUR_LABELS[index]


# ═══ Command 组件类 =====


class DeerRecordCommand(BaseCommand):
    """鹿管记录命令。"""

    command_name = "deer_pipe_record"
    command_description = "记录一次鹿管并发送个人热力图"

    def __init__(self, plugin: "DeerPipeTablePlugin", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plugin = plugin
        self.kwargs = kwargs

    async def execute(self) -> tuple[bool, str | None, int]:
        if not self._stream_id:
            return False, "无法获取聊天流信息", 0
        if not self.plugin.config.trigger.enable_record:
            return False, None, 0

        user_id = str(self.kwargs.get("user_id") or "")
        msg_dict = self.kwargs.get("message") or {}
        nickname = str(
            (msg_dict.get("message_info") or {}).get("user_info", {}).get("user_nickname", "")
        ) or (f"用户{user_id[-4:]}" if user_id else "未知")

        if not user_id:
            self.plugin.ctx.logger.warning("鹿管记录：无法获取发送者 user_id，跳过记录")
            return False, "无法识别用户身份", 0

        real_group_id = str(self.kwargs.get("group_id") or "")
        allowed = self.plugin.config.group_filter.allowed_groups
        if allowed and real_group_id not in allowed:
            return True, "非白名单群，已忽略", 2

        success = self.plugin._add_record(real_group_id, user_id, nickname)
        if not success:
            cooldown = self.plugin.config.rate_limit.cooldown_minutes
            await self.plugin.ctx.send.text(
                self.plugin.config.rate_limit.exceed_reply + f"（每{cooldown}分钟只能记录一次哦）",
                self._stream_id,
            )
            return True, "冷却期内拦截", 2

        image_base64 = await self.plugin._build_personal_heatmap_base64(
            real_group_id, user_id, nickname
        )
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self.plugin._get_monthly_stats(real_group_id, month_key)
        user_count = stats.get(user_id, {}).get("count", 0)

        if image_base64:
            await self.plugin.ctx.send.hybrid([
                {"type": "text", "content": f"记录成功！本月第{user_count}次 🦌"},
                {"type": "image", "content": image_base64},
            ], self._stream_id)
        else:
            await self.plugin.ctx.send.text(
                f"记录成功！本月第{user_count}次 🦌", self._stream_id
            )

        return True, "鹿管已记录", 2


class DeerRankCommand(BaseCommand):
    """鹿管排行榜命令。"""

    command_name = "deer_pipe_rank"
    command_description = "查询本月鹿管排行榜"

    def __init__(self, plugin: "DeerPipeTablePlugin", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plugin = plugin
        self.kwargs = kwargs

    async def execute(self) -> tuple[bool, str | None, int]:
        if not self.plugin.config.trigger.enable_rank:
            return False, None, 0

        real_group_id = str(self.kwargs.get("group_id") or "")
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self.plugin._get_monthly_stats(real_group_id, month_key)

        if not stats:
            first_trigger = self.plugin.config.trigger.deer_pipe_record_words.strip() or "🦌"
            await self.plugin.ctx.send.text(
                f"本月还没有鹿管记录哦～\n发送 {first_trigger} 来记录吧！", self._stream_id
            )
            return True, "本月无记录", 2

        sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
        total_count = sum(d["count"] for _, d in sorted_users)

        try:
            html = chart_template.build_deer_pipe_rank_chart(
                month_key, sorted_users, total_count, is_dark=self.plugin._is_dark_mode()
            )
            result = await self.plugin.ctx.render.html2png(
                html=html,
                selector="#chart-container",
                viewport={"width": 660, "height": 500},
                device_scale_factor=2.0,
                full_page=True,
                wait_until="networkidle",
            )
            image_base64 = self.plugin._extract_base64(result)
            if image_base64:
                await self.plugin.ctx.send.image(image_base64, self._stream_id)
                return True, "已发送排行榜图表", 2
        except (OSError, ValueError, RuntimeError):
            pass

        lines = [f"本月鹿管排行榜（{month_key}）", f"总次数：{total_count}", "─" * 20]
        for i, (uid, data) in enumerate(sorted_users[:10], 1):
            medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {data['nickname']}：{data['count']} 次")
        await self.plugin.ctx.send.text("\n".join(lines), self._stream_id)
        return True, "已发送排行榜", 2


class DeerPersonalCommand(BaseCommand):
    """个人统计命令。"""

    command_name = "deer_pipe_personal"
    command_description = "查询个人鹿管统计，发送热力图"

    def __init__(self, plugin: "DeerPipeTablePlugin", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plugin = plugin
        self.kwargs = kwargs

    async def execute(self) -> tuple[bool, str | None, int]:
        if not self._stream_id:
            return False, "无法获取聊天流信息", 0
        if not self.plugin.config.trigger.enable_personal:
            return False, None, 0

        user_id = str(self.kwargs.get("user_id") or "")
        msg_dict = self.kwargs.get("message") or {}
        nickname = str(
            (msg_dict.get("message_info") or {}).get("user_info", {}).get("user_nickname", "")
        ) or (f"用户{user_id[-4:]}" if user_id else "未知")

        if not user_id:
            return False, "无法识别用户身份", 0

        real_group_id = str(self.kwargs.get("group_id") or "")
        image_base64 = await self.plugin._build_personal_heatmap_base64(
            real_group_id, user_id, nickname
        )
        if image_base64:
            await self.plugin.ctx.send.hybrid([
                {"type": "text", "content": "看看这张图："},
                {"type": "image", "content": image_base64},
            ], self._stream_id)
        else:
            now = datetime.now()
            month_key = now.strftime("%Y-%m")
            stats = self.plugin._get_monthly_stats(real_group_id, month_key)
            user_data = stats.get(user_id)
            if user_data:
                sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
                rank = next(i for i, (uid, _) in enumerate(sorted_users, 1) if uid == user_id)
                streak = self.plugin._get_streak(real_group_id, user_id, month_key)["days"]
                await self.plugin.ctx.send.text(
                    f"📊 {nickname} 本月🦌管统计\n"
                    f"🦌 鹿管次数：{user_data['count']} 次\n"
                    f"🏅 排名：第 {rank} 名（共 {len(stats)} 人）\n"
                    f"🔥 最长连续打卡：{streak} 天\n"
                    f"📅 活跃天数：{len(user_data['days'])} 天",
                    self._stream_id,
                )
            else:
                first_trigger = self.plugin.config.trigger.deer_pipe_record_words.strip() or "🦌"
                await self.plugin.ctx.send.text(
                    f"{nickname or '你'} 本月还没有鹿管记录哦～\n发送 {first_trigger} 来记录吧！",
                    self._stream_id,
                )

        return True, "已发送个人统计", 2


class DeerMonthlyCommand(BaseCommand):
    """月度图表命令。"""

    command_name = "deer_pipe_monthly"
    command_description = "查询月度鹿管图表，支持上月/本月/指定月份"

    def __init__(self, plugin: "DeerPipeTablePlugin", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plugin = plugin
        self.kwargs = kwargs

    async def execute(self) -> tuple[bool, str | None, int]:
        if not self._stream_id:
            return False, "无法获取聊天流信息", 0
        if not self.plugin.config.trigger.enable_monthly:
            return False, None, 0

        raw_text = str(self.kwargs.get("text") or "").strip()
        trigger = self.plugin.config.trigger.deer_pipe_monthly_words

        now = datetime.now()
        if raw_text == f"上月{trigger}":
            month_num = now.month - 1 if now.month > 1 else 12
        elif raw_text == f"本月{trigger}" or raw_text == trigger:
            month_num = now.month
        else:
            m_str = self.matched_groups.get("m")
            if m_str:
                month_num = int(m_str)
            else:
                return False, None, 0

        real_group_id = str(self.kwargs.get("group_id") or "")
        return await self.plugin._handle_monthly_chart(self._stream_id, real_group_id, month_num)


# ═══ 鹿管插件主类 =====


class DeerPipeTablePlugin(MaiBotPlugin):
    """鹿管记录与月度统计插件。"""

    config_model = DeerPluginConfig

    # ═══ 数据层 =====

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
        """检查用户是否在冷却期内。返回 (是否在冷却中, 距离上次记录的秒数)。

        同时检查当前月和上个月的记录，防止跨月边界冷却失效。
        """
        now = datetime.now()
        cooldown = timedelta(minutes=self.config.rate_limit.cooldown_minutes)

        # 合并当月和上月记录，找到最近一次打卡时间
        month_key = now.strftime("%Y-%m")
        prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        all_records = self._load_records(group_id, month_key) + self._load_records(group_id, prev_month)

        last_ts = None
        for r in all_records:
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

    def _get_streak(self, group_id: str, user_id: str, month_key: str) -> dict:
        """计算用户在指定月份的最长连续打卡天数及加赛信息。

        返回 dict:
            {"days": int,          # 最长连续天数，0 表示无记录
             "last_day": int,      # 该连续段的最后一天 (1-31)，0 表示无记录
             "earliest_ts": str | None}  # 该段最后一天的最早打卡时间 (ISO 格式)

        内部加赛规则：同一用户有多段相同长度的最长连续时，
        取日期最近的那段（最后一天最晚的）。
        """
        records = self._load_records(group_id, month_key)

        # 收集每天所有打卡时间
        day_timestamps: dict[int, list[datetime]] = {}
        for r in records:
            if r.get("user_id") != user_id:
                continue
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                day = ts.day
                day_timestamps.setdefault(day, []).append(ts)
            except (ValueError, KeyError):
                continue

        if not day_timestamps:
            return {"days": 0, "last_day": 0, "earliest_ts": None}

        sorted_days = sorted(day_timestamps.keys())

        # best: (length, end_day, earliest_on_last_day_iso)
        best: tuple[int, int, str] | None = None
        cur_start = sorted_days[0]
        cur_end = sorted_days[0]

        def _finish_segment(start: int, end: int):
            nonlocal best
            length = end - start + 1
            earliest = min(day_timestamps[end]).isoformat()
            if best is None or length > best[0] or (length == best[0] and end > best[1]):
                best = (length, end, earliest)

        for i in range(1, len(sorted_days)):
            if sorted_days[i] == sorted_days[i - 1] + 1:
                cur_end = sorted_days[i]
            else:
                _finish_segment(cur_start, cur_end)
                cur_start = sorted_days[i]
                cur_end = sorted_days[i]

        _finish_segment(cur_start, cur_end)

        if best is None:
            return {"days": 0, "last_day": 0, "earliest_ts": None}
        return {"days": best[0], "last_day": best[1], "earliest_ts": best[2]}

    def _find_streak_king(self, group_id: str, stats: dict, month_key: str) -> tuple[str, int]:
        """评选连续打卡王。返回 (昵称, 天数)。

        优先比较最长连续天数（降序）；天数相同时比较各自连续段
        最后一天的最早打卡时间（升序）；再平局按 dict 遍历顺序取第一个。
        """
        king_name = "暂无"
        king_info: dict = {"days": 0, "last_day": 0, "earliest_ts": None}

        for uid in stats:
            info = self._get_streak(group_id, uid, month_key)
            if info["days"] == 0:
                continue
            if info["days"] > king_info["days"]:
                king_info = info
                king_name = stats[uid]["nickname"]
            elif info["days"] == king_info["days"]:
                # 加赛：最后一天打卡时间更早的胜出
                cur_ts = info.get("earliest_ts")
                king_ts = king_info.get("earliest_ts")
                if king_ts is None or (cur_ts is not None and cur_ts < king_ts):
                    king_info = info
                    king_name = stats[uid]["nickname"]

        return king_name, king_info["days"]

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

    def _get_daily_max(self, group_id: str, month_key: str) -> tuple[str, str, int]:
        """获取单日最高记录（按用户维度）。

        统计每个用户每天各自打了多少次，找出单天次数最高的用户。
        返回 (昵称, 日期, 次数)。

        加赛规则：同一日期两个用户打出相同最高次数时，
        选该日打卡时间最早的用户。
        """
        records = self._load_records(group_id, month_key)
        # key: (user_id, date_str), value: {"count": int, "earliest": datetime}
        user_day: dict[tuple[str, str], dict] = {}
        nickname_map: dict[str, str] = {}

        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
            except (ValueError, KeyError):
                continue
            uid = r["user_id"]
            date_str = ts.strftime("%m-%d")
            nickname_map[uid] = r.get("nickname", uid)
            key = (uid, date_str)
            if key not in user_day:
                user_day[key] = {"count": 0, "earliest": ts}
            user_day[key]["count"] += 1
            if ts < user_day[key]["earliest"]:
                user_day[key]["earliest"] = ts

        if not user_day:
            return "无", "无", 0

        # 主排序：次数降序；次数相同时，最早打卡时间升序
        best_key = max(
            user_day,
            key=lambda k: (user_day[k]["count"], -user_day[k]["earliest"].timestamp()),
        )
        best_uid, best_date = best_key
        return nickname_map.get(best_uid, best_uid), best_date, user_day[best_key]["count"]

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

    # ═══ 组件注册 =====

    def get_components(self) -> list[dict[str, Any]]:
        """注册 BaseCommand 子类，从配置动态构建 command_pattern。"""
        cfg = self.config.trigger

        _record = cfg.deer_pipe_record_words
        _rank = cfg.deer_pipe_rank_words
        _personal = cfg.deer_pipe_personal_words
        _monthly = cfg.deer_pipe_monthly_words

        DeerRecordCommand.command_pattern = rf"^{re.escape(_record)}$"
        DeerRankCommand.command_pattern = rf"^{re.escape(_rank)}$"
        DeerPersonalCommand.command_pattern = rf"^{re.escape(_personal)}$"
        DeerMonthlyCommand.command_pattern = (
            rf"^(?:上月{re.escape(_monthly)}"
            rf"|本月{re.escape(_monthly)}"
            rf"|{re.escape(_monthly)}\s*(?P<m>\d{{1,2}})月"
            rf"|{re.escape(_monthly)})$"
        )

        components = super().get_components()
        components = [c for c in components if c.get("type") != "command"]
        for cmd_cls in [DeerRecordCommand, DeerRankCommand, DeerPersonalCommand, DeerMonthlyCommand]:
            cmd_info = cmd_cls.get_command_info()
            handler_name = f"handle_{cmd_cls.command_name.split('_')[-1]}"
            components.append({
                "name": cmd_info.name,
                "type": cmd_info.component_type,
                "metadata": {
                    "command_pattern": cmd_info.command_pattern,
                    "description": cmd_info.description,
                    "handler_name": handler_name,
                },
            })
        return components

    # ═══ Command 委托方法 =====

    async def handle_record(self, stream_id: str = "", **kwargs: Any) -> Any:
        cmd = DeerRecordCommand(plugin=self, **kwargs)
        cmd._stream_id = stream_id
        if matched_groups := kwargs.get("matched_groups"):
            cmd.set_matched_groups(matched_groups)
        return await cmd.execute()

    async def handle_rank(self, stream_id: str = "", **kwargs: Any) -> Any:
        cmd = DeerRankCommand(plugin=self, **kwargs)
        cmd._stream_id = stream_id
        if matched_groups := kwargs.get("matched_groups"):
            cmd.set_matched_groups(matched_groups)
        return await cmd.execute()

    async def handle_personal(self, stream_id: str = "", **kwargs: Any) -> Any:
        cmd = DeerPersonalCommand(plugin=self, **kwargs)
        cmd._stream_id = stream_id
        if matched_groups := kwargs.get("matched_groups"):
            cmd.set_matched_groups(matched_groups)
        return await cmd.execute()

    async def handle_monthly(self, stream_id: str = "", **kwargs: Any) -> Any:
        cmd = DeerMonthlyCommand(plugin=self, **kwargs)
        cmd._stream_id = stream_id
        if matched_groups := kwargs.get("matched_groups"):
            cmd.set_matched_groups(matched_groups)
        return await cmd.execute()

    # ═══ 夜间模式 =====

    def _is_dark_mode(self) -> bool:
        """判断当前是否应使用夜间模式。"""
        if not self.config.dark_mode.dark_mode:
            return False
        now = datetime.now()
        start = self.config.dark_mode.dark_start
        end = self.config.dark_mode.dark_end
        if start > end:
            # 跨天区间（如 21:00-07:00）
            return now.hour >= start or now.hour < end
        return start <= now.hour < end

    # ═══ 共享辅助：个人热力图生成 =====

    async def _build_personal_heatmap_base64(
        self, stream_id: str, user_id: str, nickname: str
    ) -> str | None:
        """生成个人热力图，返回 base64 字符串。合并自原 _route_deer_record 和 _route_personal 的图片生成逻辑。"""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        stats = self._get_monthly_stats(stream_id, month_key)
        user_data = stats.get(user_id)
        if not user_data:
            return None

        user_count = user_data.get("count", 0)
        day_counts: dict[int, int] = {}
        for ts_str in user_data.get("timestamps", []):
            try:
                d = datetime.fromisoformat(ts_str).day
                day_counts[d] = day_counts.get(d, 0) + 1
            except ValueError:
                pass

        html = chart_template.build_personal_heatmap(month_key, nickname, user_count, day_counts, is_dark=self._is_dark_mode())
        result = await self.ctx.render.html2png(
            html=html,
            selector="#chart-container",
            viewport={"width": 620, "height": 520},
            device_scale_factor=2.0,
            full_page=True,
            wait_until="networkidle",
        )
        return self._extract_base64(result)

    async def _handle_monthly_chart(self, stream_id: str, group_id: str, month_num: int) -> Any:
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

        stats = self._get_monthly_stats(group_id, month_key)
        if not stats:
            await self.ctx.send.text(f"📊 {month_key} 还没有🦌管记录哦～", stream_id)
            return True, "指定月份无记录", 2

        # 生成图表
        image_base64 = await self._generate_full_report(group_id, month_key, stats)
        if image_base64:
            await self.ctx.send.image(image_base64, stream_id)
            return True, f"已发送 {month_key} 🦌管月表", 2

        # 图表生成失败时发送文本统计
        sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
        total = sum(d["count"] for _, d in sorted_users)
        lines = [f"📊 {month_key} 🦌管月表", f"🦌 总次数：{total}", "─" * 20]
        for i, (uid, data) in enumerate(sorted_users[:10], 1):
            lines.append(f"{i}. {data['nickname']}：{data['count']} 次")
        await self.ctx.send.text("\n".join(lines), stream_id)
        return True, f"已发送 {month_key} 文本统计", 2

    # ═══ 图表生成 =====

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
            streak_king_name, streak_king_count = self._find_streak_king(group_id, stats, month_key)
            all_time = self._get_all_time_stats(group_id)
            all_time_sorted = sorted(all_time.items(), key=lambda x: x[1]["count"], reverse=True)

            html = chart_template.build_full_report(
                month_key, stats, group_id, hourly, best_day,
                streak_king_name, streak_king_count, all_time_sorted,
                is_dark=self._is_dark_mode(),
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

    # ═══ 生命周期 =====

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
    """创建鹿管插件实例

    Returns:
        DeerPipeTablePlugin: 插件实例。
    """
    return DeerPipeTablePlugin()
