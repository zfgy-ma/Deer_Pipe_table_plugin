"""鹿管记录与月度统计插件 — 配置模型。

WebUI 配置表单依赖此模块生成多语言界面。
"""

from __future__ import annotations

from typing import ClassVar, Dict, Optional

from maibot_sdk import Field, PluginConfigBase

# ═══════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════

CONFIG_SCHEMA_VERSION = "1.4.0"


# ═══════════════════════════════════════════════════════════════════════
# i18n 辅助
# ═══════════════════════════════════════════════════════════════════════


def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """构造 WebUI 配置项多语言说明，外层 label/hint 保留中文字段。"""
    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n


# ═══════════════════════════════════════════════════════════════════════
# 配置模型
# ═══════════════════════════════════════════════════════════════════════


class PluginSection(PluginConfigBase):
    """插件基础设置"""

    __ui_label__: ClassVar[str] = "插件"
    __ui_icon__: ClassVar[str] = "plug"
    __ui_order__: ClassVar[int] = 0

    config_version: str = Field(
        default=CONFIG_SCHEMA_VERSION,
        description="配置 schema 版本，请勿手动修改。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "label": "配置版本",
            "i18n": _schema_i18n(
                label_en="Config version",
                label_ja="設定バージョン",
            ),
            "order": 99,
        },
    )
    enabled: bool = Field(
        default=True,
        description="总开关。关闭后插件完全停止工作，不会记录鹿管也不会响应命令。",
        json_schema_extra={
            "label": "启用插件",
            "hint": "关闭后插件完全停止工作，不会记录鹿管也不会响应命令。",
            "i18n": _schema_i18n(
                label_en="Enable plugin",
                label_ja="プラグインを有効化",
                hint_en="Master switch. When OFF, the plugin stops entirely.",
                hint_ja="マスタースイッチ。OFFにするとプラグインは完全に停止します。",
            ),
            "order": 0,
        },
    )


class TriggerSection(PluginConfigBase):
    """触发词与功能开关(修改后需要重启麦麦保存)"""

    __ui_label__: ClassVar[str] = "触发词"
    __ui_icon__: ClassVar[str] = "zap"
    __ui_order__: ClassVar[int] = 1

    enable_record: bool = Field(
        default=True,
        description="启用鹿管记录功能。关闭后发送 🦌 不会记录。",
        json_schema_extra={
            "label": "启用鹿管记录",
            "hint": "开启后群成员发送鹿管触发词（默认🦌）时会记录次数。",
            "i18n": _schema_i18n(
                label_en="Enable deer record",
                label_ja="🦌記録を有効化",
                hint_en="When ON, members sending 🦌 will be recorded.",
                hint_ja="ONにすると🦌を送信したメンバーが記録されます。",
            ),
            "order": 0,
        },
    )
    deer_pipe_record_words: str = Field(
        default="🦌",
        description="鹿管记录触发词。消息完全等于该词时记录一次。",
        json_schema_extra={
            "label": "记录触发词",
            "hint": "消息完全等于该词时记录一次鹿管。默认值：🦌",
            "placeholder": "🦌",
            "i18n": _schema_i18n(
                label_en="Record trigger word",
                label_ja="記録トリガーワード",
                hint_en="A message exactly matching this word records a check-in. Default: 🦌",
                hint_ja="この単語と完全一致するメッセージでチェックインを記録。デフォルト: 🦌",
            ),
            "order": 1,
        },
    )
    enable_rank: bool = Field(
        default=True,
        description="启用排行榜查询功能。",
        json_schema_extra={
            "label": "启用排行榜",
            "hint": "开启后用户可查询本月鹿管次数排行。",
            "i18n": _schema_i18n(
                label_en="Enable leaderboard",
                label_ja="ランキングを有効化",
                hint_en="When ON, users can query the monthly check-in leaderboard.",
                hint_ja="ONにすると月間チェックインランキングを照会できます。",
            ),
            "order": 2,
        },
    )
    deer_pipe_rank_words: str = Field(
        default="🦌排名",
        description="排行榜查询触发词。",
        json_schema_extra={
            "label": "排行触发词",
            "hint": "消息完全等于该词时查询本月排行榜。默认值：🦌排名",
            "placeholder": "🦌排名",
            "i18n": _schema_i18n(
                label_en="Leaderboard trigger word",
                label_ja="ランキングトリガーワード",
                hint_en="Message exactly matching this word queries the leaderboard. Default: 🦌排名",
                hint_ja="この単語と完全一致するメッセージでランキングを表示。デフォルト: 🦌排名",
            ),
            "order": 3,
        },
    )
    enable_personal: bool = Field(
        default=True,
        description="启用个人统计查询功能。",
        json_schema_extra={
            "label": "启用个人统计",
            "hint": "开启后用户可查询自己的鹿管热力图和统计。",
            "i18n": _schema_i18n(
                label_en="Enable personal stats",
                label_ja="個人統計を有効化",
                hint_en="When ON, users can query their own check-in heatmap.",
                hint_ja="ONにすると自分のチェックインヒートマップを照会できます。",
            ),
            "order": 4,
        },
    )
    deer_pipe_personal_words: str = Field(
        default="我的🦌",
        description="个人统计查询触发词。",
        json_schema_extra={
            "label": "个人统计触发词",
            "hint": "消息完全等于该词时查询个人本月统计。默认值：我的🦌",
            "placeholder": "我的🦌",
            "i18n": _schema_i18n(
                label_en="Personal stats trigger word",
                label_ja="個人統計トリガーワード",
                hint_en="Message matching this word queries personal monthly stats. Default: 我的🦌",
                hint_ja="この単語と一致するメッセージで個人月間統計を表示。デフォルト: 我的🦌",
            ),
            "order": 5,
        },
    )
    enable_monthly: bool = Field(
        default=True,
        description="启用月度图表查询功能。",
        json_schema_extra={
            "label": "启用月度图表",
            "hint": "开启后用户可查询月度鹿管完整报告（热力图+排行榜+趣味统计）。",
            "i18n": _schema_i18n(
                label_en="Enable monthly report",
                label_ja="月間レポートを有効化",
                hint_en="When ON, users can query the monthly full report chart.",
                hint_ja="ONにすると月間の完全レポート（ヒートマップ+ランキング+統計）を照会できます。",
            ),
            "order": 6,
        },
    )
    deer_pipe_monthly_words: str = Field(
        default="🦌表",
        description="月度图表基础词。支持「上月X」「本月X」「X N月」格式。",
        json_schema_extra={
            "label": "月表触发词",
            "hint": "月表命令的基础词。支持格式：鹿表 / 鹿表7月 / 上月鹿表 / 本月鹿表。默认值：🦌表",
            "placeholder": "🦌表",
            "i18n": _schema_i18n(
                label_en="Monthly report trigger word",
                label_ja="月間レポートトリガーワード",
                hint_en="Base word for monthly report. Supports: 鹿表, 鹿表7月, 上月鹿表, 本月鹿表. Default: 🦌表",
                hint_ja="月間レポートの基本単語。形式: 鹿表, 鹿表7月, 上月鹿表, 本月鹿表。デフォルト: 🦌表",
            ),
            "order": 7,
        },
    )


class DarkModeSection(PluginConfigBase):
    """夜间模式配置"""

    __ui_label__: ClassVar[str] = "夜间模式"
    __ui_icon__: ClassVar[str] = "moon"
    __ui_order__: ClassVar[int] = 2

    dark_mode: bool = Field(
        default=True,
        description="开启夜间模式，在夜间时段自动使用暗色图表主题。",
        json_schema_extra={
            "label": "开启夜间模式",
            "hint": "开启后在指定时间段内图表自动切换为暗色主题，保护视力。",
            "i18n": _schema_i18n(
                label_en="Enable dark mode",
                label_ja="ダークモードを有効化",
                hint_en="Automatically switches charts to dark theme during specified hours.",
                hint_ja="指定時間帯にチャートを自動的にダークテーマに切り替えます。",
            ),
            "order": 0,
        },
    )
    dark_start: int = Field(
        default=21,
        description="夜间模式开始小时（0-23）。默认 21 点。",
        json_schema_extra={
            "label": "夜间开始时间",
            "hint": "夜间模式开始的小时数（0-23）。默认 21 点开始。",
            "i18n": _schema_i18n(
                label_en="Dark mode start hour",
                label_ja="ダークモード開始時刻",
                hint_en="Hour (0-23) when dark mode starts. Default: 21.",
                hint_ja="ダークモード開始時間（0-23）。デフォルト: 21時。",
            ),
            "order": 1,
        },
    )
    dark_end: int = Field(
        default=7,
        description="夜间模式结束小时（0-23）。默认 7 点。",
        json_schema_extra={
            "label": "夜间结束时间",
            "hint": "夜间模式结束的小时数（0-23）。默认 7 点结束。支持跨天区间（如 21→7）。",
            "i18n": _schema_i18n(
                label_en="Dark mode end hour",
                label_ja="ダークモード終了時刻",
                hint_en="Hour (0-23) when dark mode ends. Default: 7. Supports overnight ranges (e.g. 21→7).",
                hint_ja="ダークモード終了時間（0-23）。デフォルト: 7時。日をまたぐ区間（例: 21→7）に対応。",
            ),
            "order": 2,
        },
    )


class RateLimitSection(PluginConfigBase):
    """限频配置"""

    __ui_label__: ClassVar[str] = "限频"
    __ui_icon__: ClassVar[str] = "timer"
    __ui_order__: ClassVar[int] = 3

    cooldown_minutes: int = Field(
        default=120,
        description="每次记录之间的冷却时间（分钟）。",
        json_schema_extra={
            "label": "冷却时间（分钟）",
            "hint": "同一个人两次鹿管记录之间至少间隔的分钟数。默认 120 分钟（2小时）。",
            "i18n": _schema_i18n(
                label_en="Cooldown (minutes)",
                label_ja="クールダウン（分）",
                hint_en="Minimum minutes between two check-ins by the same person. Default: 120. (2 hours)",
                hint_ja="同じ人のチェックイン間隔の最小分数。デフォルト: 120分。(2時間)",
            ),
            "order": 0,
        },
    )
    exceed_reply: str = Field(
        default="注意身体，歇会儿吧！",
        description="超过限频时的自动回复内容。",
        json_schema_extra={
            "label": "超限回复语",
            "hint": "冷却期内再次打卡时的自动回复。",
            "placeholder": "注意身体，歇会儿吧！",
            "i18n": _schema_i18n(
                label_en="Cooldown reply",
                label_ja="クールダウン返信",
                hint_en="Auto-reply when checking in during cooldown period.",
                hint_ja="クールダウン中にチェックインした場合の自動返信。",
            ),
            "order": 1,
        },
    )


class RetentionSection(PluginConfigBase):
    """数据保留配置"""

    __ui_label__: ClassVar[str] = "数据保留"
    __ui_icon__: ClassVar[str] = "archive"
    __ui_order__: ClassVar[int] = 4

    months: int = Field(
        default=2,
        description="数据保留月数。超过此月数的旧数据文件会被清理。",
        json_schema_extra={
            "label": "保留月数",
            "hint": "超过此月数的旧数据会在插件加载时自动清理。默认保留 2 个月。",
            "i18n": _schema_i18n(
                label_en="Retention months",
                label_ja="保持月数",
                hint_en="Old data files older than this are auto-cleaned on plugin load. Default: 2 months.",
                hint_ja="この月数を超える古いデータはプラグイン読み込み時に自動削除。デフォルト: 2ヶ月。",
            ),
            "order": 0,
        },
    )
    auto_cleanup: bool = Field(
        default=True,
        description="是否在插件加载时自动清理过期数据。",
        json_schema_extra={
            "label": "自动清理",
            "hint": "开启后每次插件加载时自动删除超过保留期限的数据文件。",
            "i18n": _schema_i18n(
                label_en="Auto cleanup",
                label_ja="自動クリーンアップ",
                hint_en="When ON, expired data files are auto-deleted on each plugin load.",
                hint_ja="ONにするとプラグイン読み込み時に期限切れデータを自動削除。",
            ),
            "order": 1,
        },
    )


class GroupFilterSection(PluginConfigBase):
    """群过滤配置（白名单模式）"""

    __ui_label__: ClassVar[str] = "群过滤"
    __ui_icon__: ClassVar[str] = "users"
    __ui_order__: ClassVar[int] = 5

    allowed_groups: list[str] = Field(
        default_factory=list,
        description="白名单群号列表。留空表示允许所有群。",
        json_schema_extra={
            "label": "白名单群号",
            "hint": "只有列表中的群号才会被记录和响应。留空 = 允许所有群。每行一个群号。",
            "placeholder": "123456789",
            "i18n": _schema_i18n(
                label_en="Allowed group IDs",
                label_ja="許可グループID",
                hint_en="Only groups in this list are recorded. Empty = allow all groups. One per line.",
                hint_ja="このリストのグループのみ記録。空欄 = すべてのグループを許可。1行に1つ。",
            ),
            "order": 0,
        },
    )


class DeerPluginConfig(PluginConfigBase):
    """鹿管插件完整配置"""

    plugin: PluginSection = Field(default_factory=PluginSection)
    trigger: TriggerSection = Field(default_factory=TriggerSection)
    dark_mode: DarkModeSection = Field(default_factory=DarkModeSection)
    rate_limit: RateLimitSection = Field(default_factory=RateLimitSection)
    retention: RetentionSection = Field(default_factory=RetentionSection)
    group_filter: GroupFilterSection = Field(default_factory=GroupFilterSection)


DeerPluginConfig.model_rebuild()
