# SPDX-License-Identifier: GPL-3.0-or-later
"""Design-space geometry and palette copied from UIArt/ReInodeUI.svg."""
from pathlib import Path
import sys

from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon
from PyQt5.QtWidgets import QApplication


def _theme_root():
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for candidate in (meipass, meipass / "gui"):
            if (candidate / "assets").is_dir():
                return candidate
        return meipass
    return Path(__file__).resolve().parent


ROOT = _theme_root()
ASSETS = ROOT / "assets"
ICONS = ASSETS / "icons"
APP_ICON_PNG = ICONS / "app" / "pulse.png"
APP_ICON_ICO = ICONS / "app" / "app.ico"
DESIGN_SVG = ASSETS / "design.svg"

# SVG artboard origin of the main chrome.
OX, OY = 412.67, 465.23
WIN_W, WIN_H = 2131.54, 3165.55
MAIN_VIEW = (OX, OY, WIN_W, WIN_H)
# Window size is a fraction of the usable desktop, not a fixed pixel box.
HEIGHT_FRACTION = 0.60
WIDTH_FRACTION = 0.30
SCREEN_MARGIN = 48
REF_SCREEN = (1920, 1080)
OUTER_R = 109.71
INNER = (467.96 - OX, 512.44 - OY, 2020.97, 3068.95, 104.02)

BANNER = (597.88 - OX, 0.0, 681.61, 76.18, 19.04)
TITLE = (633.39 - OX, 520.03 - OY)
VERSION = (1119.32 - OX, 518.51 - OY)
APP_VERSION = "1.3.18"


def _w(items):
    return [(c, x - OX, y - OY) for c, x, y in items]


G_BANNER = _w([
    ("开", 633.389, 520.033), ("源", 677.694, 520.033), ("暨", 721.999, 520.033),
    ("珠", 766.304, 520.033), ("有", 810.609, 520.033), ("线", 854.914, 520.033),
    ("网", 899.219, 520.033), ("络", 943.524, 520.033), ("终", 987.828, 520.033),
    ("端", 1032.133, 520.033),
])
G_LOGIN_TITLE = _w([
    ("网", 614.263, 821.421), ("络", 714.957, 821.421), ("登", 815.650, 821.421), ("入", 916.344, 821.421),
])
G_LOGIN_BADGE = _w([
    ("[", 1021.126, 821.421), ("8", 1040.208, 821.421), ("0", 1070.915, 821.421),
    ("2", 1101.622, 821.421), (".", 1132.328, 821.421), ("1", 1148.504, 821.421),
    ("X", 1179.211, 821.421), ("连", 1211.947, 821.421), ("接", 1265.136, 821.421), ("]", 1318.324, 821.421),
])
G_ACCOUNT = _w([("账", 619.768, 966.223), ("号", 705.985, 966.223)])
G_PASSWORD = _w([("密", 619.777, 1253.709), ("码", 705.675, 1253.709)])
G_SAVE_ACC = _w([("保", 996.112, 1552.650), ("存", 1058.049, 1552.650), ("账", 1119.985, 1552.650), ("号", 1181.921, 1552.650)])
G_SAVE_PWD = _w([("保", 1527.415, 1553.405), ("存", 1589.351, 1553.405), ("密", 1651.288, 1553.405), ("码", 1713.224, 1553.405)])
G_SETTINGS_BAR = _w([("设", 620.492, 1866.177), ("置", 721.185, 1866.177)])
G_SPEED = _w([("网", 618.100, 2150.995), ("络", 703.998, 2150.995), ("测", 789.896, 2150.995), ("速", 875.795, 2150.995)])
G_RECOVERY = _w([("无", 780.072, 2973.570), ("感", 865.970, 2973.570), ("重", 951.869, 2973.570), ("连", 1037.767, 2973.570)])
CLOSE_C = (2440.47 - OX, 568.97 - OY, 103.75)
CLOSE_ICON = (2395.77 - OX, 521.90 - OY, 90.0, 90.0)

LOGIN = (547.50 - OX, 657.46 - OY, 1611.72, 968.86, 92.61)
LOGIN_TITLE = (614.3 - OX, 821.4 - OY)
LOGIN_BADGE = (1021.1 - OX, 821.4 - OY)
ACCOUNT_L = (619.8 - OX, 966.2 - OY)
ACCOUNT_BOX = (622.26 - OX, 999.52 - OY, 1383.64, 142.36, 63.85)
ACCOUNT_PH = (674.1 - OX, 1091.8 - OY)
PASSWORD_L = (619.8 - OX, 1253.7 - OY)
PASSWORD_BOX = (622.26 - OX, 1289.08 - OY, 1383.64, 131.20, 58.85)
PASSWORD_PH = (674.1 - OX, 1375.9 - OY)
EYE = (1861.29 - OX, 1306.19 - OY, 97.0, 97.0)
SAVE_ACC_ICON = (890.92 - OX, 1485.05 - OY, 88.0, 88.0)
SAVE_ACC_L = (996.1 - OX, 1552.7 - OY)
SAVE_PWD_ICON = (1417.81 - OX, 1485.05 - OY, 88.0, 88.0)
SAVE_PWD_L = (1527.4 - OX, 1553.4 - OY)

SETTINGS_BAR = (547.50 - OX, 1713.56 - OY, 1877.42, 227.83, 111.12)
SETTINGS_L = (620.5 - OX, 1866.2 - OY)
SETTINGS_CHEV = (2201.28 - OX, 1777.00 - OY, 118.0, 101.0)

SPEED = (545.82 - OX, 2007.23 - OY, 1877.42, 722.33, 65.51)
SPEED_L = (618.1 - OX, 2151.0 - OY)
UP_ICON = (1883.30 - OX, 2094.49 - OY, 60.0, 60.0)
UP_L = (1955.2 - OX, 2151.0 - OY)
DOWN_ICON = (2158.34 - OX, 2094.49 - OY, 60.0, 60.0)
DOWN_L = (2222.8 - OX, 2151.0 - OY)
SPARK = (545.82 - OX, 2246.37 - OY, 1877.42, 483.20, 43.82)
SPARK_LINE = [
    (490.776 - OX, 2548.126 - OY),
    (801.596 - OX, 2303.926 - OY),
    (933.250 - OX, 2521.149 - OY),
    (1112.438 - OX, 2373.714 - OY),
    (1291.363 - OX, 2560.559 - OY),
    (1596.099 - OX, 2564.664 - OY),
    (1724.215 - OX, 2373.714 - OY),
    (1915.237 - OX, 2481.856 - OY),
    (1981.682 - OX, 2601.845 - OY),
    (2219.974 - OX, 2483.967 - OY),
    (2331.845 - OX, 2373.714 - OY),
    (2417.102 - OX, 2490.184 - OY),
    (2487.013 - OX, 2560.559 - OY),
]

RECOVERY = (545.82 - OX, 2814.80 - OY, 650.91, 623.75, 59.62)
RECOVERY_TITLE = (780.1 - OX, 2973.6 - OY)
RECOVERY_STATUS = (781.5 - OX, 3028.5 - OY)
RECOVERY_SHIELD = (575.0 - OX, 2875.0 - OY, 153.0, 187.0)
TIMELINE = [
    ((591.6 - OX, 3158.7 - OY), (853.6 - OX, 3158.7 - OY), (1057.19 - OX, 3123.56 - OY)),
    ((591.6 - OX, 3243.7 - OY), (853.6 - OX, 3241.9 - OY), (1060.22 - OX, 3206.71 - OY)),
    ((591.6 - OX, 3328.7 - OY), (853.6 - OX, 3328.7 - OY), (1060.22 - OX, 3293.55 - OY)),
]
TIME_RULES = [3105.256 - OY, 3188.186 - OY, 3268.428 - OY, 3351.938 - OY]
TIME_RULE_X = 545.821 - OX
TIME_RULE_W = 650.911

AD = (1253.39 - OX, 2814.80 - OY, 1175.06, 623.75, 59.62)
AD_LOGO = (1265.32 - OX, 2826.22 - OY, 445.92, 153.07)
AD_GO = (2168.1 - OX, 2919.8 - OY)
AD_HEAD = (1290.5 - OX, 3016.3 - OY)
AD_HEAD_PREFIX = "作者使用"
AD_HEAD_LINK = "tree.reverix.ai"
AD_HEAD_SUFFIX = "的AI服务开发"
AD_HEAD_SIZE = 55.54
AD_BULLETS = [
    (1364.5 - OX, 3089.1 - OY, "·提供世界顶级的大模型接入[GPT/Claude/Grok等]"),
    (1364.5 - OX, 3139.9 - OY, "·中国大陆优化线路，稳定连接"),
    (1364.5 - OX, 3192.0 - OY, "·全正价号池"),
    (1364.5 - OX, 3243.6 - OY, "·使用数据全程零接触零保留零分发，保证安全"),
    (1364.5 - OX, 3295.0 - OY, "·为全国多家知名高校科研项目组提供服务"),
    (1364.5 - OX, 3347.9 - OY, "·可开发票"),
    (1559.7 - OX, 3347.9 - OY, "·人工客服支持"),
    (1617.6 - OX, 3191.7 - OY, "·业内领先的性价比"),
]
AD_THANKS = (2042.0 - OX, 3410.0 - OY)
DISCLAIMER = (620.0 - OX, 3520.0 - OY)

LED_BTN = (2224.38 - OX, 805.26 - OY, 200.54, 197.38, 49.35)
IN_BTN = (2224.38 - OX, 1043.48 - OY, 200.54, 197.38, 49.35)
OUT_BTN = (2224.38 - OX, 1281.13 - OY, 200.54, 197.38, 49.35)

# Settings card in its own design space.
SX, SY = 2593.51, 1661.95
SET_W, SET_H = 1502.49, 1968.83
SET_VIEW = (SX, SY, SET_W, SET_H)
SET_R = 77.33
SET_TITLE = (2677.7 - SX, 1825.5 - SY)


def _s(items):
    return [(c, x - SX, y - SY) for c, x, y in items]


G_SET_TITLE = _s([("设", 2677.680, 1825.492), ("置", 2778.374, 1825.492)])
G_SET_NIC = _s([("选", 2728.142, 2000.421), ("择", 2796.272, 2000.421), ("网", 2864.402, 2000.421), ("卡", 2932.532, 2000.421)])
G_SET_TYPE = _s([("连", 2727.546, 2379.203), ("接", 2795.676, 2379.203), ("类", 2863.806, 2379.203), ("型", 2931.936, 2379.203)])
G_SET_AUTO = _s([("自", 2739.257, 2805.798), ("动", 2807.387, 2805.798), ("操", 2875.516, 2805.798), ("作", 2943.646, 2805.798)])
SET_NIC_BOX = (2676.28 - SX, 1885.34 - SY, 1336.94, 327.78, 81.94)
SET_NIC_L = (2728.1 - SX, 2000.4 - SY)
SET_NIC_FIELD = (2707.14 - SX, 2042.91 - SY, 1275.24, 132.31, 47.67)
SET_NIC_TEXT = (2751.4 - SX, 2122.8 - SY)
SET_CARET = (3837.8 - SX, 2083.72 - SY, 90.0, 52.0)
SET_TYPE_BOX = (2676.28 - SX, 2258.39 - SY, 1336.94, 373.25, 110.69)
SET_TYPE_L = (2727.5 - SX, 2379.2 - SY)
SET_TYPE_BTNS = [
    (2728.39 - SX, 2445.01 - SY, 372.90, 128.70, 38.17, "普通连接"),
    (3158.82 - SX, 2445.01 - SY, 371.86, 128.70, 38.17, "快速认证连接"),
    (3587.03 - SX, 2445.01 - SY, 371.86, 128.70, 38.17, "单点登录连接"),
]
SET_TYPE_TEXT_Y = 2528.5 - SY
SET_AUTO_BOX = (2676.28 - SX, 2676.92 - SY, 1336.94, 877.22, 122.55)
SET_AUTO_L = (2739.3 - SX, 2805.8 - SY)
SET_AUTOS = [
    (2745.80 - SX, 2892.93 - SY, "开机后自动启动(默认)", "auto_start"),
    (2745.80 - SX, 3007.78 - SY, "自启动后不显示主面板", "silent_start"),
    (2745.80 - SX, 3122.53 - SY, "有线网络接入时自动尝试连接(默认)", "auto_connect"),
    (2745.80 - SX, 3235.07 - SY, "流量异常时自动尝试重新连接(默认)", "auto_reconnect"),
    (2745.80 - SX, 3338.62 - SY, "会话保活(beta) · 尚未支持", "seamless"),
    (2745.80 - SX, 3453.47 - SY, "学校官方客户端自动重连兜底", "inode_fallback"),
]
SET_AUTO_ICON = (74.0, 70.0)
SET_AUTO_TEXT_DX = 2851.7 - 2745.80
SET_AUTO_TEXT_DY = 2952.1 - 2892.93

C_OUTER = QColor("#444444")
C_INNER = QColor("#242424")
C_CARD = QColor("#181818")
C_FIELD = QColor("#242424")
C_STROKE = QColor("#444444")
C_LINE = QColor("#7c7c7c")
C_TEXT = QColor("#c7c7c7")
C_MUTED = QColor("#818181")
C_SOFT = QColor("#c6c6c6")
C_DIM = QColor(199, 199, 199, 115)
C_THANKS = QColor("#848484")
C_GREEN = QColor("#16c60c")
C_SPARK = QColor("#c6c6c6")


def pick_font_family():
    families = QFontDatabase().families()
    for name in ("Source Han Sans SC", "Source Han Sans CN", "Noto Sans SC", "HarmonyOS Sans SC",
                 "Microsoft YaHei UI", "Microsoft YaHei"):
        if name in families:
            return name
    return QApplication.font().family()


def app_icon():
    for candidate in (APP_ICON_ICO, APP_ICON_PNG):
        if candidate.is_file():
            return QIcon(str(candidate))
    return QIcon()


def _bundled_font_paths():
    names = ("SourceHanSansSC-Bold.otf", "SourceHanSansSC-Regular.otf", "SourceHanSansCN-Normal.ttf")
    roots = []
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe))
        roots.extend((exe / "fonts", meipass / "gui" / "assets" / "fonts", meipass / "assets" / "fonts"))
    else:
        roots.append(Path(__file__).resolve().parent / "assets" / "fonts")
    for root in roots:
        for name in names:
            yield root / name


def load_design_font():
    paths = list(_bundled_font_paths()) + [
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "SourceHanSansSC-Bold.otf",
        Path(r"C:\Windows\Fonts\SourceHanSansCN-Normal.ttf"),
    ]
    for path in paths:
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if not exists:
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            return families[0]
    return pick_font_family()


def ui_font(px, scale, family):
    font = QFont(family)
    font.setPixelSize(max(1, round(px * scale)))
    font.setWeight(QFont.Bold)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def window_pixel_size(avail_w, avail_h):
    inner_w = max(1, avail_w - SCREEN_MARGIN)
    inner_h = max(1, avail_h - SCREEN_MARGIN)
    height = inner_h * HEIGHT_FRACTION
    width = height * (WIN_W / WIN_H)
    max_width = inner_w * WIDTH_FRACTION
    if width > max_width:
        width = max_width
        height = width * (WIN_H / WIN_W)
    if height > inner_h:
        height = inner_h
        width = height * (WIN_W / WIN_H)
    if width > inner_w:
        width = inner_w
        height = width * (WIN_H / WIN_W)
    return width, height


def window_scale(screen):
    if screen is None:
        width, _height = window_pixel_size(*REF_SCREEN)
        return max(0.05, width / WIN_W)
    geo = screen.availableGeometry()
    width, _height = window_pixel_size(geo.width(), geo.height())
    return max(0.05, width / WIN_W)
