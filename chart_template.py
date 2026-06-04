"""鹿管插件图表 HTML 模板。

提供三种图表的纯 HTML/CSS 模板：
- 个人月度热力图（🦌 回复用）
- 月度完整报告（X月鹿表用）
- 鹿王排行榜柱状图（鹿王命令用）

所有模板为纯 HTML 内联 CSS，不依赖外部资源，供 render.html2png() 渲染。
"""

from __future__ import annotations

import calendar as _cal
from collections import defaultdict
from datetime import datetime, timedelta


def build_personal_heatmap(month_key: str, user_nickname: str, user_count: int, day_counts: dict, is_dark: bool = False) -> str:
    """构建个人月度活跃热力图 HTML（含本周回顾模块）。

    Args:
        month_key: 月份标识，如 "2026-06"。
        user_nickname: 用户昵称。
        user_count: 用户本月总次数。
        day_counts: 每日次数字典 {day(int): count(int)}。
    """
    import calendar as _cal
    from collections import defaultdict as _dd

    parts = month_key.split("-")
    year, month = int(parts[0]), int(parts[1])
    first_day = datetime(year, month, 1)
    last_day_num = _cal.monthrange(year, month)[1]
    first_weekday = first_day.weekday()

    # 补齐无记录日期
    full_counts: dict[int, int] = {d: day_counts.get(d, 0) for d in range(1, last_day_num + 1)}
    max_day_count = max(full_counts.values()) if full_counts else 1

    # ---- 本周回顾数据 ----
    today = datetime.now()
    weekday_today = today.weekday()
    week_start = today - timedelta(days=weekday_today)
    week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    week_cards = ""
    for i in range(7):
        wday = week_start + timedelta(days=i)
        wday_num = wday.day
        wday_name = week_names[i]
        wcount = full_counts.get(wday_num, 0) if wday.month == month else 0
        if wcount >= 5:
            cls = "count-max"
        elif wcount > 0:
            cls = f"count-{wcount}"
        else:
            cls = "count-0"
        week_cards += '<div class="date-item ' + cls + '">'
        week_cards += '<span class="day-name">' + wday_name + '</span>'
        week_cards += '<span class="bold-white-text">' + str(wcount) + '</span>'
        week_cards += '</div>'

    # ---- 热力图单元格 ----
    cells_html = ""
    for _ in range(first_weekday):
        cells_html += '<div class="heatmap-cell empty"></div>'
    for day in range(1, last_day_num + 1):
        count = full_counts.get(day, 0)
        level = min(count, 5) if count > 0 else 0
        cells_html += '<div class="heatmap-cell level-' + str(level) + '">'
        cells_html += '<span class="date-label">' + str(day) + '</span>'
        if count >= 5:
            cells_html += '<span class="bold-white-text">' + str(count) + '</span>'
        cells_html += '</div>'
    total_cells = first_weekday + last_day_num
    remainder = total_cells % 7
    if remainder > 0:
        for _ in range(7 - remainder):
            cells_html += '<div class="heatmap-cell empty"></div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:#ffffff; display:flex; justify-content:center; align-items:center;
    min-height:100vh; color:#333; padding:40px;
}}
.container {{
    background:#ffffff; border:1px solid #eaeaea; border-radius:16px;
    padding:40px; box-shadow:0 10px 40px rgba(0,0,0,0.03);
    display:flex; flex-direction:column; align-items:center; gap:24px;
    max-width:600px; width:100%;
}}
.header {{ text-align:center; margin-bottom:4px; }}
.header h2 {{ font-size:18px; font-weight:700; color:#333; }}
.header p {{ font-size:14px; color:#8c8c8c; margin-top:2px; }}
/* 本周回顾 */
.date-list-header {{ width:100%; display:flex; flex-direction:column; gap:8px; }}
.date-list-title {{ font-size:14px; font-weight:600; color:#8c8c8c; padding-left:4px; }}
.date-list-container {{ width:100%; display:flex; gap:8px; }}
.date-item {{ flex:1; height:56px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:3px; }}
.date-item .day-name {{ font-size:12px; font-weight:500; color:rgba(255,255,255,0.85); }}
.count-0 {{ background-color:#f3f4f6; }} .count-0 .day-name {{ color:#9ca3af; }} .count-0 .bold-white-text {{ color:#9ca3af; text-shadow:none; }}
.count-1 {{ background-color:#fef9c3; }} .count-1 .day-name {{ color:#92400e; }} .count-1 .bold-white-text {{ color:#333333; text-shadow:none; }}
.count-2 {{ background-color:#fde68a; }} .count-2 .day-name {{ color:#92400e; }} .count-2 .bold-white-text {{ color:#333333; text-shadow:none; }}
.count-3 {{ background-color:#fb923c; }}
.count-4 {{ background-color:#ef4444; }}
.count-max {{ background-color:#b91c1c; }}
/* 本月足迹 */
.heatmap-section {{ display:flex; flex-direction:column; align-items:center; gap:12px; width:100%; }}
.heatmap-month-title {{ font-size:15px; font-weight:700; color:#333; }}
.heatmap-weekdays {{ display:grid; grid-template-columns:repeat(7,48px); gap:10px; text-align:center; margin-bottom:4px; }}
.weekday-label {{ font-size:13px; font-weight:600; color:#8c8c8c; }}
.heatmap-grid {{ display:grid; grid-template-columns:repeat(7,48px); gap:10px; }}
.heatmap-cell {{
    width:48px; height:48px; border-radius:8px; background-color:#f3f4f6;
    position:relative; display:flex; justify-content:center; align-items:center;
}}
.date-label {{ position:absolute; top:4px; left:5px; font-size:11px; font-weight:600; line-height:1; }}
.bold-white-text {{
    font-size:18px; font-weight:800; color:#ffffff; line-height:1;
    text-shadow:0 1px 2px rgba(0,0,0,0.1);
}}
.level-0 {{ background-color:#f3f4f6; }} .level-0 .date-label {{ color:#9ca3af; }}
.level-1 {{ background-color:#fef9c3; }} .level-1 .date-label {{ color:#92400e; }}
.level-2 {{ background-color:#fde68a; }} .level-2 .date-label {{ color:#92400e; }}
.level-3 {{ background-color:#fb923c; }} .level-3 .date-label {{ color:rgba(255,255,255,0.85); }}
.level-4 {{ background-color:#ef4444; }} .level-4 .date-label {{ color:rgba(255,255,255,0.85); }}
.level-5 {{ background-color:#b91c1c; }} .level-5 .date-label {{ color:rgba(255,255,255,0.85); }}
.heatmap-cell.empty {{ background-color:transparent; }}
.legend-container {{ display:flex; align-items:center; font-size:13px; color:#8c8c8c; gap:12px; margin-top:4px; }}
.legend-squares {{ display:flex; gap:6px; }}
.legend-square {{ width:18px; height:18px; border-radius:4px; }}
.count-footer {{ text-align:center; }}
.count-footer span {{ font-size:14px; color:#8c8c8c; }}
.count-footer .count-num {{ font-size:20px; font-weight:800; color:#ef4444; }}
body.dark {{ background:#1D1D1D; color:#e5e5e5; }}
body.dark .container {{ background:#2a2a2a; border-color:#3d3d3d; box-shadow:0 10px 40px rgba(0,0,0,0.3); }}
body.dark .header h1, body.dark .header h2, body.dark .heatmap-month-title {{ color:#e5e5e5; }}
body.dark .header p, body.dark .weekday-label, body.dark .date-list-title {{ color:#a0a0a0; }}
body.dark .level-0 {{ background-color:#333333; }} body.dark .level-0 .date-label {{ color:#999999; }}
body.dark .count-0 {{ background-color:#333333; }} body.dark .count-0 .day-name {{ color:#888888; }} body.dark .count-0 .bold-white-text {{ color:#888888; text-shadow:none; }}
body.dark .stat-card {{ background:#2a2a2a; border-color:#3d3d3d; }}
body.dark .stat-card .value {{ color:#e5e5e5; }}
body.dark .alltime-table th, body.dark .alltime-table td {{ border-color:#3d3d3d; color:#e5e5e5; }}
body.dark .section-title {{ color:#e5e5e5; border-color:#3d3d3d; }}
body.dark .count-footer span, body.dark .legend-container {{ color:#a0a0a0; }}
body.dark .bar-track {{ background:#3d3d3d; }}
body.dark .bar-stat, body.dark .bar-name, body.dark .bar-label {{ color:#e5e5e5; }}
body.dark .bar-stat-days, body.dark .footer {{ color:#a0a0a0; }}
body.dark .heatmap-cell.empty {{ background-color:transparent; }}
</style>
</head>
<body{' class="dark"' if is_dark else ''}>
<div id="chart-container">
<div class="container">
<div class="header">
    <h2>🦌{user_nickname} 的本月鹿管足迹</h2>
    <p>{year}年{month}月</p>
</div>
<div class="date-list-header">
    <div class="date-list-title">本周回顾</div>
    <div class="date-list-container">{week_cards}</div>
</div>
<div class="heatmap-section">
    <div class="heatmap-month-title">{year}年{month}月</div>
    <div class="heatmap-weekdays">
        <div class="weekday-label">一</div><div class="weekday-label">二</div><div class="weekday-label">三</div>
        <div class="weekday-label">四</div><div class="weekday-label">五</div><div class="weekday-label">六</div><div class="weekday-label">日</div>
    </div>
    <div class="heatmap-grid">{cells_html}</div>
    <div class="legend-container">
        <span>0次</span>
        <div class="legend-squares">
            <div class="legend-square level-0"></div><div class="legend-square level-1"></div>
            <div class="legend-square level-2"></div><div class="legend-square level-3"></div>
            <div class="legend-square level-4"></div><div class="legend-square level-5"></div>
        </div>
        <span>5次及以上</span>
    </div>
</div>
<div class="count-footer">
    <span>本月累计 <span class="count-num">{user_count}</span> 次</span>
</div>
</div>
</div>
</body>
</html>"""

def build_deer_pipe_rank_chart(month_key: str, sorted_users: list, total: int, is_dark: bool = False) -> str:
    """构建鹿王排行榜柱状图 HTML。

    Args:
        month_key: 月份标识，如 "2026-06"。
        sorted_users: [(user_id, {nickname, count, days}), ...] 按次数降序，取 Top 10。
        total: 本月总鹿管次数。
    """
    top10 = sorted_users[:10]
    max_count = top10[0][1]["count"] if top10 else 1
    parts = month_key.split("-")

    bar_rows = ""
    colors = [
        "#b91c1c", "#c13228", "#c84934", "#d05f41", "#d7764d",
        "#df8c59", "#e6a365", "#eeb971", "#f6d07e", "#fde68a",
    ]
    medals = ["🥇", "🥈", "🥉", "4", "5", "6", "7", "8", "9", "10"]
    for i, (_uid, data) in enumerate(top10):
        pct = int(data["count"] / max(max_count, 1) * 100)
        color = colors[i % len(colors)]
        safe_name = data["nickname"].replace("<", "&lt;").replace(">", "&gt;")
        active_days = len(data.get("days", []))
        bar_rows += f"""
        <div class="bar-row">
            <span class="bar-rank">{medals[i]}</span>
            <span class="bar-name">{safe_name}</span>
            <div class="bar-track">
                <div class="bar-fill" style="width:{pct}%;background:{color};"></div>
            </div>
            <span class="bar-stat">{data['count']} 次</span>
            <span class="bar-stat-days">{active_days} 天</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:#ffffff; display:flex; justify-content:center; align-items:center;
    min-height:100vh; color:#333; padding:40px;
}}
.container {{
    background:#ffffff; border:1px solid #eaeaea; border-radius:16px;
    padding:40px; box-shadow:0 10px 40px rgba(0,0,0,0.03);
    max-width:640px; width:100%;
}}
.header {{ text-align:center; margin-bottom:28px; }}
.header h1 {{ font-size:22px; font-weight:700; color:#333; }}
.header p {{ font-size:14px; color:#8c8c8c; margin-top:6px; }}
.bar-row {{ display:flex; align-items:center; margin:8px 0; gap:10px; }}
.bar-rank {{ width:32px; text-align:center; font-size:16px; font-weight:700; flex-shrink:0; }}
.bar-name {{ width:110px; font-size:13px; text-align:right; flex-shrink:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.bar-track {{ flex:1; height:28px; background:#f3f4f6; border-radius:6px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:6px; min-width:4px; }}
.bar-stat {{ width:44px; font-size:13px; font-weight:600; color:#333; flex-shrink:0; text-align:right; }}
.bar-stat-days {{ width:36px; font-size:11px; color:#9ca3af; flex-shrink:0; text-align:right; }}
.footer {{ text-align:center; margin-top:24px; font-size:13px; color:#8c8c8c; }}
body.dark {{ background:#1D1D1D; color:#e5e5e5; }}
body.dark .container {{ background:#2a2a2a; border-color:#3d3d3d; box-shadow:0 10px 40px rgba(0,0,0,0.3); }}
body.dark .header h1, body.dark .header h2, body.dark .heatmap-month-title {{ color:#e5e5e5; }}
body.dark .header p, body.dark .weekday-label, body.dark .date-list-title {{ color:#a0a0a0; }}
body.dark .level-0 {{ background-color:#333333; }} body.dark .level-0 .date-label {{ color:#999999; }}
body.dark .count-0 {{ background-color:#333333; }} body.dark .count-0 .day-name {{ color:#888888; }} body.dark .count-0 .bold-white-text {{ color:#888888; text-shadow:none; }}
body.dark .stat-card {{ background:#2a2a2a; border-color:#3d3d3d; }}
body.dark .stat-card .value {{ color:#e5e5e5; }}
body.dark .alltime-table th, body.dark .alltime-table td {{ border-color:#3d3d3d; color:#e5e5e5; }}
body.dark .section-title {{ color:#e5e5e5; border-color:#3d3d3d; }}
body.dark .count-footer span, body.dark .legend-container {{ color:#a0a0a0; }}
body.dark .bar-track {{ background:#3d3d3d; }}
body.dark .bar-stat, body.dark .bar-name, body.dark .bar-label {{ color:#e5e5e5; }}
body.dark .bar-stat-days, body.dark .footer {{ color:#a0a0a0; }}
body.dark .heatmap-cell.empty {{ background-color:transparent; }}
</style>
</head>
<body{' class="dark"' if is_dark else ''}>
<div id="chart-container">
<div class="container">
<div class="header">
    <h1>🦌 {parts[0]}年{int(parts[1])}月 鹿管排行榜</h1>
    <p>总鹿管次数：{total} 次 | 参与人数：{len(sorted_users)} 人</p>
</div>
{bar_rows}
<div class="footer">数据截止至当月 | 排名 次数 活跃天数</div>
</div>
</div>
</body>
</html>"""


def build_full_report(
    month_key: str,
    stats: dict,
    group_id: str,
    hourly: dict,
    best_day: tuple,
    streak_king_name: str,
    streak_king_count: int,
    all_time_sorted: list,
    is_dark: bool = False,
) -> str:
    """构建月度完整报告 HTML（X月鹿表用）。

    包含：每日活跃热力图 + Top 10 柱状图 + 趣味统计 + 历史总榜。

    Args:
        month_key: 月份标识。
        stats: 月度统计数据，{user_id: {nickname, count, days, timestamps}}。
        group_id: 群标识（用于统计）。
        hourly: 时段分布字典。
        best_day: (昵称, 日期, 次数) 单日最高。
        streak_king_name: 连续打卡王昵称。
        streak_king_count: 连续打卡王天数。
        all_time_sorted: 历史总榜 [(user_id, {nickname, count, days}), ...]。
    """
    from collections import defaultdict as _dd

    sorted_users = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(d["count"] for _, d in sorted_users)
    top10 = sorted_users[:10]
    max_count = top10[0][1]["count"] if top10 else 1

    parts = month_key.split("-")
    year, month = int(parts[0]), int(parts[1])
    first_day = datetime(year, month, 1)
    last_day_num = _cal.monthrange(year, month)[1]
    first_weekday = first_day.weekday()

    # 每日计数
    day_counts: dict[int, int] = _dd(int)
    for _uid, data in stats.items():
        for day in data["days"]:
            day_counts[day] += 1
    max_day_count = max(day_counts.values()) if day_counts else 1

    # 热力图
    cells_html = ""
    for _ in range(first_weekday):
        cells_html += '<div class="heatmap-cell empty"></div>'
    for day in range(1, last_day_num + 1):
        count = day_counts.get(day, 0)
        level = min(count, 5) if count > 0 else 0
        cells_html += f'<div class="heatmap-cell level-{level}">'
        cells_html += f'<span class="date-label">{day}</span>'
        if count >= 5:
            cells_html += f'<span class="bold-white-text">{count}</span>'
        cells_html += "</div>"
    total_cells = first_weekday + last_day_num
    remainder = total_cells % 7
    if remainder > 0:
        for _ in range(7 - remainder):
            cells_html += '<div class="heatmap-cell empty"></div>'

    # 柱状图
    bar_colors = [
        "#b91c1c", "#c13228", "#c84934", "#d05f41", "#d7764d",
        "#df8c59", "#e6a365", "#eeb971", "#f6d07e", "#fde68a",
    ]
    bar_rows = ""
    for i, (_uid, data) in enumerate(top10):
        pct = int(data["count"] / max(max_count, 1) * 100)
        color = bar_colors[i % len(bar_colors)]
        safe_name = data["nickname"].replace("<", "&lt;").replace(">", "&gt;")
        bar_rows += f"""
        <div class="bar-row">
            <span class="bar-label">{i + 1}. {safe_name}</span>
            <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color};"></div></div>
            <span class="bar-count">{data['count']} 次</span>
        </div>"""

    # 时段统计
    peak_label = max(hourly, key=lambda k: hourly[k])
    peak_count = hourly[peak_label]
    peak_short = peak_label.split("(")[0] if "(" in peak_label else peak_label

    # 历史总榜
    all_time_rows = ""
    for i, (_uid, data) in enumerate(all_time_sorted[:5], 1):
        safe_name = data["nickname"].replace("<", "&lt;").replace(">", "&gt;")
        all_time_rows += f"<tr><td>{i}</td><td>{safe_name}</td><td>{data['count']} 次</td></tr>"
    if not all_time_rows:
        all_time_rows = '<tr><td colspan="3" style="color:#999;">暂无历史数据</td></tr>'

    safe_streak_name = streak_king_name.replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:#ffffff; color:#333; padding:24px; width:780px;
}}
.header {{ text-align:center; margin-bottom:20px; }}
.header h1 {{ font-size:24px; color:#333; }}
.header p {{ font-size:14px; color:#8c8c8c; margin-top:4px; }}
.section-title {{ font-size:16px; font-weight:600; color:#333; margin:16px 0 8px; padding-bottom:4px; border-bottom:1px solid #eaeaea; }}
/* 热力图 (参考风格) */
.heatmap {{ display:grid; grid-template-columns:repeat(7,48px); gap:10px; margin-bottom:16px; justify-content:center; }}
.weekday {{ text-align:center; font-size:13px; font-weight:600; color:#8c8c8c; padding:4px 0; }}
.heatmap-cell {{
    width:48px; height:48px; border-radius:8px; background-color:#f3f4f6;
    position:relative; display:flex; justify-content:center; align-items:center;
}}
.date-label {{ position:absolute; top:4px; left:5px; font-size:11px; font-weight:600; line-height:1; }}
.bold-white-text {{ font-size:18px; font-weight:800; color:#fff; line-height:1; text-shadow:0 1px 2px rgba(0,0,0,0.1); }}
.level-0 {{ background-color:#f3f4f6; }} .level-0 .date-label {{ color:#9ca3af; }}
.level-1 {{ background-color:#fef9c3; }} .level-1 .date-label {{ color:#92400e; }}
.level-2 {{ background-color:#fde68a; }} .level-2 .date-label {{ color:#92400e; }}
.level-3 {{ background-color:#fb923c; }} .level-3 .date-label {{ color:rgba(255,255,255,0.85); }}
.level-4 {{ background-color:#ef4444; }} .level-4 .date-label {{ color:rgba(255,255,255,0.85); }}
.level-5 {{ background-color:#b91c1c; }} .level-5 .date-label {{ color:rgba(255,255,255,0.85); }}
.heatmap-cell.empty {{ background-color:transparent; }}
/* 柱状图 */
.bar-row {{ display:flex; align-items:center; margin:6px 0; gap:8px; }}
.bar-label {{ width:130px; font-size:13px; text-align:right; flex-shrink:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.bar-track {{ flex:1; height:22px; background:#f3f4f6; border-radius:4px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:4px; }}
.bar-count {{ width:50px; font-size:12px; color:#8c8c8c; flex-shrink:0; }}
/* 趣味统计 */
.stats-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:12px 0; }}
.stat-card {{ background:#f9fafb; border:1px solid #eaeaea; border-radius:10px; padding:14px; text-align:center; }}
.stat-card .value {{ font-size:18px; font-weight:bold; color:#333; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.stat-card .label {{ font-size:11px; color:#8c8c8c; margin-top:4px; }}
/* 总榜表格 */
.alltime-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.alltime-table th, .alltime-table td {{ padding:6px 10px; text-align:left; border-bottom:1px solid #eaeaea; }}
.alltime-table th {{ color:#8c8c8c; font-weight:normal; font-size:11px; }}
.legend-container {{ display:flex; align-items:center; font-size:13px; color:#8c8c8c; gap:12px; margin-top:4px; }}
.legend-squares {{ display:flex; gap:6px; }}
.legend-square {{ width:18px; height:18px; border-radius:4px; }}
.weekday-row {{ display:grid; grid-template-columns:repeat(7,48px); gap:10px; text-align:center; margin-bottom:4px; justify-content:center; }}
body.dark {{ background:#1D1D1D; color:#e5e5e5; }}
body.dark .container {{ background:#2a2a2a; border-color:#3d3d3d; box-shadow:0 10px 40px rgba(0,0,0,0.3); }}
body.dark .header h1, body.dark .header h2, body.dark .heatmap-month-title {{ color:#e5e5e5; }}
body.dark .header p, body.dark .weekday-label, body.dark .date-list-title {{ color:#a0a0a0; }}
body.dark .level-0 {{ background-color:#333333; }} body.dark .level-0 .date-label {{ color:#999999; }}
body.dark .count-0 {{ background-color:#333333; }} body.dark .count-0 .day-name {{ color:#888888; }} body.dark .count-0 .bold-white-text {{ color:#888888; text-shadow:none; }}
body.dark .stat-card {{ background:#2a2a2a; border-color:#3d3d3d; }}
body.dark .stat-card .value {{ color:#e5e5e5; }}
body.dark .alltime-table th, body.dark .alltime-table td {{ border-color:#3d3d3d; color:#e5e5e5; }}
body.dark .section-title {{ color:#e5e5e5; border-color:#3d3d3d; }}
body.dark .count-footer span, body.dark .legend-container {{ color:#a0a0a0; }}
body.dark .bar-track {{ background:#3d3d3d; }}
body.dark .bar-stat, body.dark .bar-name, body.dark .bar-label {{ color:#e5e5e5; }}
body.dark .bar-stat-days, body.dark .footer {{ color:#a0a0a0; }}
body.dark .heatmap-cell.empty {{ background-color:transparent; }}
</style>
</head>
<body{' class="dark"' if is_dark else ''}>
<div id="chart-container">
<div class="header">
    <h1>🦌 {month_key} 月度鹿管报告</h1>
    <p>总次数：{total} | 参与人数：{len(stats)} 人</p>
</div>

<div class="section-title">📅 每日活跃热力图</div>
<div class="weekday-row">
    <div class="weekday">一</div><div class="weekday">二</div><div class="weekday">三</div>
    <div class="weekday">四</div><div class="weekday">五</div><div class="weekday">六</div><div class="weekday">日</div>
</div>
<div class="heatmap">{cells_html}</div>
<div class="legend-container">
    <span>0次</span>
    <div class="legend-squares">
        <div class="legend-square level-0"></div><div class="legend-square level-1"></div>
        <div class="legend-square level-2"></div><div class="legend-square level-3"></div>
        <div class="legend-square level-4"></div><div class="legend-square level-5"></div>
    </div>
    <span>5次及以上</span>
</div>

<div class="section-title">🏆 本月鹿管王 Top 10</div>
{bar_rows}

<div class="section-title">📈 趣味统计</div>
<div class="stats-grid">
    <div class="stat-card">
        <div class="value">{peak_short}</div>
        <div class="label">最活跃时段（{peak_count} 次）</div>
    </div>
    <div class="stat-card">
        <div class="value">{best_day[0]}</div>
        <div class="label">{best_day[1]} · {best_day[2]} 次</div>
    </div>
    <div class="stat-card">
        <div class="value">{safe_streak_name}</div>
        <div class="label">连续打卡王（{streak_king_count} 天）</div>
    </div>
    <div class="stat-card">
        <div class="value">{len(stats)} 人</div>
        <div class="label">本月参与人数</div>
    </div>
</div>

<div class="section-title">📜 历史总榜 Top 5</div>
<table class="alltime-table">
    <tr><th>排名</th><th>昵称</th><th>总次数</th></tr>
    {all_time_rows}
</table>
</div>
</body>
</html>"""
