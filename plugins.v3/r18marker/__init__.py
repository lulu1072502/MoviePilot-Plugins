"""识别结果 R18 标志 + 识别词一键写入。

三块能力：

1. **识别结果清单**（整理历史 / 下载历史 / 订阅）
   数据来自宿主稳定的只读查询 SDK ``app.sdk.queries``，每条带媒体身份
   （``media_source`` + ``media_id``）。

2. **R18 判定**
   优先按 TMDB **关键词** 判定（默认 ``198385`` = hentai，可在配置里改），
   读 ``/tv/{id}/keywords``、``/movie/{id}/keywords``；关键词接口不可用时回退到
   TMDB 详情里的 ``adult`` 字段。判定结果按 TTL 缓存，其它数据源（豆瓣/Bangumi 等）
   没有等价字段，显示「未判定」，不伪造标记。

3. **识别词一键写入**
   内置经 TMDB 逐条核对生成的**全量**识别词快照（192 条 `{[tmdbid=…;type=tv|movie;…]}` 绑定规则 + 13 条通用清理规则），
   通过 ``/identifiers/status``、``/identifiers/preview``、``/identifiers/apply``
   三个接口与页面按钮，**合并**写入宿主 ``SystemConfigKey.CustomIdentifiers``
   （已存在的规则不重复添加，不动用户已有规则）。

页面为 Vuetify JSON 模式，由 MoviePilot 前端内置 ``PageRender`` 渲染。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.sdk.logging import logger
from app.sdk.queries import (
    MAX_QUERY_PAGE_SIZE,
    QueryPageRequest,
    list_download_history,
    list_subscriptions,
    list_transfer_history,
)

# 宿主内置数据来源编号（等价于 MediaSource.TMDB = "themoviedb"）
_TMDB_SOURCE = "themoviedb"
# 媒体类型中文 -> TMDB 路径段
_MEDIA_TYPE_PATH = {"电影": "movie", "电视剧": "tv", "系列": "collection", "音乐": "movie"}
# TMDB hentai 关键词（可配置）
_DEFAULT_HENTAI_KEYWORD = 198385
# R18 判定结果缓存有效期（秒）
_ADULT_TTL_SECONDS = 7 * 24 * 3600
# 判定缓存条目上限
_ADULT_CACHE_LIMIT = 2000
# 判定缓存存放键
_CACHE_KEY = "adult_cache"
# 每类来源最多显示的条数
_MAX_COUNT = min(50, int(MAX_QUERY_PAGE_SIZE))

# 来源分组
_SOURCE_ALL = "全部"
_SOURCE_TRANSFER = "整理历史"
_SOURCE_DOWNLOAD = "下载历史"
_SOURCE_SUBSCRIBE = "订阅"
_SOURCE_OPTIONS: Tuple[str, ...] = (_SOURCE_ALL, _SOURCE_TRANSFER, _SOURCE_DOWNLOAD, _SOURCE_SUBSCRIBE)
_GROUPED_SOURCES: Tuple[str, ...] = (_SOURCE_TRANSFER, _SOURCE_DOWNLOAD, _SOURCE_SUBSCRIBE)

# 进程内复用的宿主 TMDB 客户端
_TMDB_LOCK = RLock()
_TMDB_CLIENT: Optional[Any] = None

# 内置识别规则（由 TMDB 核对生成；# 开头的注释行在识别时会被跳过）
_BUILTIN_IDENTIFIERS: Tuple[str, ...] = (
    # --- 逐条 TMDB 绑定规则（由 TMDB 逐条核对生成，快照 2026-09-27）---
    "^\\[\\d{6}\\]\\[[^\\]]+\\]サレ妻は奪われたい.*?～クールママが溺れるまで…….*$ => {[tmdbid=323604;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]告白\\.\\.\\.\\.\\.\\..*?～ギャル三昧.*$ => {[tmdbid=222931;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 彼女催眠.*?＃1.*$ => {[tmdbid=326731;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 彼女催眠.*?＃2.*$ => {[tmdbid=326731;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ピュアホリック.*?～純潔乙女と婚姻カンケイ!？.*?上巻.*$ => {[tmdbid=323836;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ピュアホリック.*?～純潔乙女と婚姻カンケイ!？.*?下巻.*$ => {[tmdbid=323836;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]霧中ノ塔.*?第2話.*$ => {[tmdbid=315133;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]蹂躙王国.*?～エルフ王国は巨大苗床に.*$ => {[tmdbid=318800;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]小女ラムネ.*?第7話.*$ => {[tmdbid=85174;type=tv;s=1;e=7]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]1LDK＋J系 いきなり同居？密着!？初エッチ!!？.*?第8話.*$ => {[tmdbid=228367;type=tv;s=1;e=8]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ヌきヌき ずっぽしイズム.*?後編.*$ => {[tmdbid=315950;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハーレム島へようこそ！.*?第1話.*$ => {[tmdbid=320889;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]so_low.*?～生意気ツン妹粗相.*$ => {[tmdbid=228360;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 田舎にはこれくらいしか娯楽がない.*?＃1.*$ => {[tmdbid=324672;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 田舎にはこれくらいしか娯楽がない.*?＃2.*$ => {[tmdbid=324672;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]デコ×デコ THE ANIMATION.*?第1巻.*$ => {[tmdbid=322604;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]デコ×デコ THE ANIMATION.*?第2巻.*$ => {[tmdbid=322604;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ファントム・アルケミア.*?～シルヴィアのドキドキ搾精都市計画.*?第2話.*$ => {[tmdbid=309084;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ラブはギャルから始まる運命.*?後編.*$ => {[tmdbid=310641;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]1LDK＋J系 いきなり同居？密着!？初エッチ!!？.*?第7話.*$ => {[tmdbid=228367;type=tv;s=1;e=7]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ヌきヌき ずっぽしイズム.*?前編.*$ => {[tmdbid=315950;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]とどの妻り.*?～美沙子…….*$ => {[tmdbid=312487;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハメハラ.*?～それセクハラですっ.*$ => {[tmdbid=317686;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA フラチ.*?＃1.*$ => {[tmdbid=320888;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA フラチ.*?＃2.*$ => {[tmdbid=320888;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]彼の知らない秘密を入れて。 THE ANIMATION.*$ => {[tmdbid=318182;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]○○交配.*?第十一話.*$ => {[tmdbid=98947;type=tv;s=1;e=11]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]痴魅悶凌.*?後編.*$ => {[tmdbid=310640;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]アナルマニアオタクとアナニー大好きなお嬢様.*?～奇跡のマッチング.*?後編.*$ => {[tmdbid=307529;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]L’amour fou de l’automate.*?～目覚める吐息.*$ => {[tmdbid=306708;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA パイハメ家族.*?＃1.*$ => {[tmdbid=318049;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA パイハメ家族.*?＃2.*$ => {[tmdbid=318049;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA はーとまーく多め。.*?＃1.*$ => {[tmdbid=318048;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA はーとまーく多め。.*?＃2.*$ => {[tmdbid=318048;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]性指導員のお仕事 The Animation.*?1時限目.*$ => {[tmdbid=315350;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]レイカは華麗な僕の女王 THE ANIMATION.*?第4巻.*$ => {[tmdbid=297313;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]剣鬼バルゴ.*?第2話.*$ => {[tmdbid=306710;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]霧中ノ塔.*?第1話.*$ => {[tmdbid=315133;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ラブはギャルから始まる運命.*?前編.*$ => {[tmdbid=310641;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]痴魅悶凌.*?前編.*$ => {[tmdbid=310640;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ちょろ・めす・でいず.*?第2話.*$ => {[tmdbid=296399;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ボクの理想の異世界生活.*?第4話.*$ => {[tmdbid=288154;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]とどの妻り.*?～義母さん…….*$ => {[tmdbid=312487;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]告白…….*?～腹黒クールギャルのサク略.*$ => {[tmdbid=222931;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]レイカは華麗な僕の女王 THE ANIMATION.*?第3巻.*$ => {[tmdbid=297313;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖光閃姫ポニーセレス.*?第2話.*$ => {[tmdbid=303948;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 巨乳が2人いないと勃起しない夫のために友達を連れてきた妻.*?＃1.*$ => {[tmdbid=315132;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 巨乳が2人いないと勃起しない夫のために友達を連れてきた妻.*?＃2.*$ => {[tmdbid=315132;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]制服は着たままで.*?後編.*$ => {[tmdbid=300447;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]アナルマニアオタクとアナニー大好きなお嬢様.*?～奇跡のマッチング.*?前編.*$ => {[tmdbid=307529;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハニーブロンド2.*?第4話.*$ => {[tmdbid=300147;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]クール de M.*?～崩れないオンナ.*$ => {[tmdbid=301686;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA ケガレボシ.*?紫.*$ => {[tmdbid=305178;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA ケガレボシ.*?黒.*$ => {[tmdbid=305178;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]蛇と蜘蛛.*$ => {[tmdbid=308398;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ファントム・アルケミア.*?～シルヴィアのドキドキ搾精都市計画.*?第1話.*$ => {[tmdbid=309084;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖宝晶華セイントライムVN.*?～VeasTubeエロエロ配信Edition♪.*?第2話.*$ => {[tmdbid=301687;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]牝を狩る村.*?後編.*$ => {[tmdbid=300148;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]夏と箱.*?第2話.*$ => {[tmdbid=300450;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハニーブロンド2.*?第3話.*$ => {[tmdbid=300147;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]L’amour fou de l’automate.*?～微かな息吹.*$ => {[tmdbid=306708;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ドSなペット.*?～イジワルな躾け.*$ => {[tmdbid=299235;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA シスターブリーダー.*?＃3.*$ => {[tmdbid=297314;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA シスターブリーダー.*?＃4.*$ => {[tmdbid=297314;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]もう一度、してみたい。.*$ => {[tmdbid=307528;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]剣鬼バルゴ.*?第1話.*$ => {[tmdbid=306710;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]制服は着たままで.*?前編.*$ => {[tmdbid=300447;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]これってナ～ニ？.*?～可愛ママ啜り啼き.*$ => {[tmdbid=295024;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 今泉ん家はどうやらギャルの溜まり場になってるらしい.*?＃5.*$ => {[tmdbid=130802;type=tv;s=1;e=5]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 今泉ん家はどうやらギャルの溜まり場になってるらしい.*?＃6.*$ => {[tmdbid=130802;type=tv;s=1;e=6]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ながちち永井さん THE ANIMATION.*?Vol\\.3.*$ => {[tmdbid=298953;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖光閃姫ポニーセレス.*?第1話.*$ => {[tmdbid=303948;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖痕のアリア.*?第2話.*$ => {[tmdbid=296868;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ママ喝っ.*?～姉ママの言い訳.*$ => {[tmdbid=212536;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA イクイク サキュバス再教育.*?＃1.*$ => {[tmdbid=278083;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA イクイク サキュバス再教育.*?＃2.*$ => {[tmdbid=278083;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]彼女フェイス THE ANIMATION.*?第1巻.*$ => {[tmdbid=275645;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]彼女フェイス THE ANIMATION.*?第2巻.*$ => {[tmdbid=275645;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]メカ技師リスタの大冒険.*?第2話.*$ => {[tmdbid=261339;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]魔法闘姫リルスティア.*?第三話.*$ => {[tmdbid=231791;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]おにちちハーレム.*?第2話.*$ => {[tmdbid=271230;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]肉園.*?第1巻.*$ => {[tmdbid=276284;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]子作り妊活部！.*?第2話.*$ => {[tmdbid=234257;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]エロリーマン へっぽこ高飛車・梨々香.*?～妄想罵りダイアリー.*$ => {[tmdbid=158206;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]少年が大人になった夏.*?第四話.*$ => {[tmdbid=261335;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]卑触家のルール.*?～不都合な盛り合せ.*$ => {[tmdbid=263109;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 野々原柚花のヒミツのハイシン.*?＃1.*$ => {[tmdbid=279519;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 野々原柚花のヒミツのハイシン.*?＃2.*$ => {[tmdbid=279519;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]知らないこと知りたいの？ THE ANIMATION.*?第1巻.*$ => {[tmdbid=278085;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]知らないこと知りたいの？ THE ANIMATION.*?第2巻.*$ => {[tmdbid=278085;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]勇者ちゃんの冒険は終わってしまった！.*?第一話.*$ => {[tmdbid=278255;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]完堕ち×寝取られ家族 The Animation 前編 ～アナタ、許して。私たち、浮気セックスに本気でハマっちゃったの～.*$ => {[tmdbid=276282;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]亜人がお好きなんですね.*?第1話.*$ => {[tmdbid=276283;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハメツの誘惑.*?～クールな押し掛けッ娘.*$ => {[tmdbid=280622;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 夕顔.*$ => {[tmdbid=282234;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 夢見ル乙女.*?＃3.*$ => {[tmdbid=272955;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]楽園侵触 Island of the dead.*?下巻.*$ => {[tmdbid=222928;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]インモラルーティーン THE ANIMATION.*$ => {[tmdbid=281035;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]育精.*?第2話.*$ => {[tmdbid=274726;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]魔法闘姫リルスティア.*?第四話.*$ => {[tmdbid=231791;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]セックスが好きで好きで大好きなクラスメイトのあの娘.*?第4話.*$ => {[tmdbid=261333;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]憧れの女上司が、相部屋出張の隣のベッドで絶倫男に寝取られている.*?第1話.*$ => {[tmdbid=282233;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]おにちちハーレム.*?第3話.*$ => {[tmdbid=271230;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]肉園.*?第2巻.*$ => {[tmdbid=276284;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]DearestBlue.*?～デレドル.*$ => {[tmdbid=249108;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]甘いイジワル.*?～地味なパパ喝.*$ => {[tmdbid=283294;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 風紀委員とフーゾク活動.*?＃1.*$ => {[tmdbid=284897;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 風紀委員とフーゾク活動.*?＃2.*$ => {[tmdbid=284897;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]異世界来たのでスケベスキルで全力謳歌しようと思う THE ANIMATION.*?第5巻.*$ => {[tmdbid=215221;type=tv;s=1;e=5]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]異世界来たのでスケベスキルで全力謳歌しようと思う THE ANIMATION.*?第6巻.*$ => {[tmdbid=215221;type=tv;s=1;e=6]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]のっと・せくさろいど・エウリィ！.*?第1話.*$ => {[tmdbid=283295;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ボクの理想の異世界生活.*?第1話.*$ => {[tmdbid=288154;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]亜人がお好きなんですね.*?第2話.*$ => {[tmdbid=276283;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]完堕ち×寝取られ家族 The Animation 後編 ～アナタ、許して。私たち、浮気セックスに本気でハマっちゃったの～.*$ => {[tmdbid=276282;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ママ喝っ.*?～姉ママの矜持.*$ => {[tmdbid=212536;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA いまりあ.*?＃5.*$ => {[tmdbid=259214;type=tv;s=1;e=5]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA いまりあ.*?＃6.*$ => {[tmdbid=259214;type=tv;s=1;e=6]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]淫触王デマール 第一章.*?～被虐の聖女ロザリア.*$ => {[tmdbid=286047;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]勇者ちゃんの冒険は終わってしまった！.*?第二話.*$ => {[tmdbid=278255;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]サキュバス★コネクト！.*?第3話.*$ => {[tmdbid=246703;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]黒ギャルアラカルト.*?1.*$ => {[tmdbid=286049;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]憧れの女上司が、相部屋出張の隣のベッドで絶倫男に寝取られている.*?第2話.*$ => {[tmdbid=282233;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]おにちちハーレム.*?第4話.*$ => {[tmdbid=271230;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]1LDK＋J系 いきなり同居？密着!？初エッチ!!？.*?第5話.*$ => {[tmdbid=228367;type=tv;s=1;e=5]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]朝まで汁だく母娘丼!!.*?前編.*$ => {[tmdbid=286050;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]エロリーマン ナマイキポジロン・梨々香.*?～2穴百合緩手.*$ => {[tmdbid=158206;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハメツの誘惑.*?～パパ慣れしっとりパイ.*$ => {[tmdbid=280622;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA トナリノカノジョ.*$ => {[tmdbid=295124;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA ヨゴレタカノジョ.*$ => {[tmdbid=297828;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]エルフに淫紋を付ける本 The Animation LEVEL：2.*$ => {[tmdbid=270832;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]元カレとはできなかったセックスしてもいいですか？.*$ => {[tmdbid=1733856;type=movie]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]プリンセスバースト！.*?～危険日の種付け孕ませ羞恥バトル！.*?第1話.*$ => {[tmdbid=287468;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]彼女がセパレートをまとう理由を見る.*$ => {[tmdbid=293126;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]神聖昂燐ダクリュオン・ルナ 後編 ～堕聖母誕生～.*$ => {[tmdbid=274724;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]黒ギャルアラカルト.*?2.*$ => {[tmdbid=286049;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]小女ラムネ.*?第5話.*$ => {[tmdbid=85174;type=tv;s=1;e=5]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]朝まで汁だく母娘丼!!.*?後編.*$ => {[tmdbid=286050;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]今日は指輪を外すから…….*?～悪いのは……ワタシ.*$ => {[tmdbid=290201;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]淫モラル・ゲームマスター THE ANIMATION.*?第1巻.*$ => {[tmdbid=289822;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]淫モラル・ゲームマスター THE ANIMATION.*?第2巻.*$ => {[tmdbid=289822;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]のっと・せくさろいど・エウリィ！.*?第2話.*$ => {[tmdbid=283295;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]サキュバス★コネクト！.*?第4話.*$ => {[tmdbid=246703;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ボクの理想の異世界生活.*?第2話.*$ => {[tmdbid=288154;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]好色の忠義くノ一ぼたん 其の壱.*$ => {[tmdbid=290998;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]社畜シンデレラ.*?～あん・リアル.*$ => {[tmdbid=292504;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]甘いイジワル.*?～友パパナメ搾り.*$ => {[tmdbid=283294;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVAピュアピュア ぺろぺろ プリンセス.*?＃1.*$ => {[tmdbid=294740;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVAピュアピュア ぺろぺろ プリンセス.*?＃2.*$ => {[tmdbid=294740;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]無人駅 The Animation 1番ホーム.*$ => {[tmdbid=292829;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]搾精病棟 THE ANIMATION 第10巻 ～アマミヤオオツカ編～.*$ => {[tmdbid=124867;type=tv;s=1;e=10]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]勇者姫ミリア.*?第三話.*$ => {[tmdbid=237539;type=tv;s=1;e=3]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]小女ラムネ.*?第6話.*$ => {[tmdbid=85174;type=tv;s=1;e=6]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]寝取られた爆乳妻たち.*?前編.*$ => {[tmdbid=292291;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]これってナ～ニ？.*?～可愛ママ搾り.*$ => {[tmdbid=295024;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA シスターブリーダー.*?＃1.*$ => {[tmdbid=297314;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA シスターブリーダー.*?＃2.*$ => {[tmdbid=297314;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]無人駅 The Animation 2番ホーム.*$ => {[tmdbid=292829;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]らぶみー『かくれんぼ』 THE ANIMATION.*$ => {[tmdbid=295025;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]プリンセスバースト！.*?～危険日の種付け孕ませ羞恥バトル！.*?第2話.*$ => {[tmdbid=287468;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]危険な森 おにごっこ.*?第一話.*$ => {[tmdbid=238280;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]寝取られた爆乳妻たち.*?後編.*$ => {[tmdbid=292291;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ちょろ・めす・でいず.*?第1話.*$ => {[tmdbid=296399;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハニーブロンド2.*?第1話.*$ => {[tmdbid=300147;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]レイカは華麗な僕の女王 THE ANIMATION.*?第1巻.*$ => {[tmdbid=297313;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]レイカは華麗な僕の女王 THE ANIMATION.*?第2巻.*$ => {[tmdbid=297313;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]DearestBlue.*?～ハメドル.*$ => {[tmdbid=249108;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]社畜シンデレラ.*?～陰・リアル.*$ => {[tmdbid=292504;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 夏妻.*?#1.*$ => {[tmdbid=299611;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA 夏妻.*?#2.*$ => {[tmdbid=299611;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]Hな義姉シリーズ The Animation 1 弟の性欲処理は、姉がするものだと お義姉ちゃんは思っている。.*$ => {[tmdbid=299035;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖痕のアリア.*?第1話.*$ => {[tmdbid=296868;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]牝を狩る村.*?前編.*$ => {[tmdbid=300148;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]1LDK＋J系 いきなり同居？密着!？初エッチ!!？.*?第6話.*$ => {[tmdbid=228367;type=tv;s=1;e=6]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]好色の忠義くノ一ぼたん 其の弐.*$ => {[tmdbid=290998;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ドSなペット.*?～初めての躾け.*$ => {[tmdbid=299235;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA おしかけ！爆乳ギャルハーレム性活.*?＃1.*$ => {[tmdbid=302911;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA おしかけ！爆乳ギャルハーレム性活.*?＃2.*$ => {[tmdbid=302911;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ながちち永井さん THE ANIMATION.*?Vol\\.1.*$ => {[tmdbid=298953;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]メイド教育。-没落貴族 瑠璃川椿- THE ANIMATION.*?第2巻.*$ => {[tmdbid=224165;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]勇者姫ミリア.*?第四話.*$ => {[tmdbid=237539;type=tv;s=1;e=4]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]危険な森 おにごっこ.*?第二話.*$ => {[tmdbid=238280;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ハニーブロンド2.*?第2話.*$ => {[tmdbid=300147;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]夏と箱.*?第1話.*$ => {[tmdbid=300450;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]クール de M.*?～乱れないオンナ.*$ => {[tmdbid=301686;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]今日は指輪を外すから…….*?～戻れない……カラダ.*$ => {[tmdbid=290201;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]Hな義姉シリーズ The Animation 2 友達が羨むHすぎる僕のママとお姉ちゃんは、ところかまわず僕を誘惑をしてきます。.*$ => {[tmdbid=299035;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ながちち永井さん THE ANIMATION.*?Vol\\.2.*$ => {[tmdbid=298953;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]異世界来たのでスケベスキルで全力謳歌しようと思う THE ANIMATION.*?第7巻.*$ => {[tmdbid=215221;type=tv;s=1;e=7]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]聖宝晶華セイントライムVN.*?～VeasTubeエロエロ配信Edition♪.*?第1話.*$ => {[tmdbid=301687;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA ケガレボシ・.*?赤.*$ => {[tmdbid=305178;type=tv;s=1;e=2]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]OVA ケガレボシ・.*?青.*$ => {[tmdbid=305178;type=tv;s=1;e=1]}",
    "^\\[\\d{6}\\]\\[[^\\]]+\\]ボクの理想の異世界生活.*?第3話.*$ => {[tmdbid=288154;type=tv;s=1;e=3]}",
    # --- 通用清理规则（识别词按顺序匹配，通用规则必须排在绑定规则之后）---
    "^\\[\\d{6}\\]\\[[^\\]]+\\]",
    "^OVA\\s*",
    "\\s*THE ANIMATION\\b",
    "\\s*The Animation\\b",
    "＃\\s*(\\d+) => 第\\1話",
    "[#]\\s*(\\d+) => 第\\1話",
    "Vol\\.\\s*(\\d+) => 第\\1話",
    "VOL\\.\\s*(\\d+) => 第\\1話",
    "(\\d+)時限目 => 第\\1話",
    "\\.{2,}(?=\\s*[～~]) => ……",
    "\\[\\s*\\]",
    "【\\s*】",
    "（\\s*）",
)


@dataclass(frozen=True)
class _Row:
    """一行识别结果及其 R18 判定。"""

    source: str
    title: str
    year: str
    mtype: str
    date: str
    media_source: Optional[str]
    media_id: Optional[str]
    adult: Optional[bool]
    r18_source: str


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    """把配置值安全地夹到 [low, high] 范围。"""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _text(value: Any) -> str:
    """把可能为空的值规范为字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _tmdb_client() -> Optional[Any]:
    """惰性获取宿主 TMDB 客户端；宿主结构变化时返回 None 而不是抛异常。"""
    global _TMDB_CLIENT
    with _TMDB_LOCK:
        if _TMDB_CLIENT is not None:
            return _TMDB_CLIENT
        try:
            from app.modules.themoviedb.tmdbapi import TmdbApi
        except Exception as err:  # pragma: no cover - 取决于宿主结构
            logger.error(f"R18标志：导入宿主 TMDB 客户端失败：{err}")
            return None
        try:
            _TMDB_CLIENT = TmdbApi()
        except Exception as err:
            logger.error(f"R18标志：初始化宿主 TMDB 客户端失败：{err}")
            return None
        return _TMDB_CLIENT


def _to_int(value: Any) -> Optional[int]:
    """安全转 int。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _fetch_tmdb_keywords(media_id: str, mtype: str) -> Optional[List[int]]:
    """读取 TMDB 关键词 ID 列表；失败返回 None（区别于「没有关键词」）。"""
    tmdbid = _to_int(media_id)
    if tmdbid is None:
        return None
    path_types = [mtype] if mtype in ("movie", "tv") else ["tv", "movie"]
    client = _tmdb_client()

    # 路径一：宿主内置 TMDB 客户端的通用请求入口
    if client is not None:
        inner = getattr(client, "tmdb", None)
        request_obj = getattr(inner, "_request_obj", None) if inner is not None else None
        if callable(request_obj):
            for one in path_types:
                try:
                    data = request_obj(f"{one}/{tmdbid}/keywords")
                except Exception as err:  # 单个类型失败不致命
                    logger.debug(f"R18标志：查询 TMDB 关键词失败（{one}/{tmdbid}）：{err}")
                    continue
                keywords = _keywords_from_payload(data)
                if keywords is not None:
                    return keywords

    # 路径二：直连 TMDB HTTP 接口（需要运行时设置里有 API Key）
    return _fetch_tmdb_keywords_http(tmdbid, path_types)


def _keywords_from_payload(data: Any) -> Optional[List[int]]:
    """从关键词响应里取出 ID 列表。"""
    if isinstance(data, dict):
        data = data.get("results", data.get("keywords"))
    if not isinstance(data, list):
        return None
    keywords: List[int] = []
    for item in data:
        if isinstance(item, dict):
            kid = _to_int(item.get("id"))
            if kid is not None:
                keywords.append(kid)
    return keywords


def _fetch_tmdb_keywords_http(tmdbid: int, path_types: List[str]) -> Optional[List[int]]:
    """直连 TMDB 关键词接口，作为宿主客户端不可用时的回退。"""
    try:
        from app.sdk.config import settings  # type: ignore

        api_key = _text(getattr(settings, "TMDB_API_KEY", ""))
        domain = _text(getattr(settings, "TMDB_API_DOMAIN", "")) or "api.themoviedb.org"
    except Exception as err:
        logger.debug(f"R18标志：读取 TMDB 运行时设置失败：{err}")
        return None
    if not api_key:
        return None
    try:
        import requests

        for one in path_types:
            try:
                resp = requests.get(
                    f"https://{domain}/3/{one}/{tmdbid}/keywords",
                    params={"api_key": api_key},
                    timeout=10,
                )
            except Exception as err:
                logger.debug(f"R18标志：HTTP 查询 TMDB 关键词失败（{one}/{tmdbid}）：{err}")
                continue
            if resp.status_code != 200:
                continue
            keywords = _keywords_from_payload(resp.json())
            if keywords is not None:
                return keywords
    except Exception as err:
        logger.debug(f"R18标志：requests 不可用：{err}")
    return None


def _fetch_tmdb_adult(media_id: str) -> Optional[bool]:
    """按 TMDB ID 读取详情里的 adult 字段；查询失败返回 None。"""
    client = _tmdb_client()
    if client is None:
        return None
    tmdbid = _to_int(media_id)
    if tmdbid is None:
        return None
    try:
        info = client.get_info(mtype=None, tmdbid=tmdbid)
    except Exception as err:  # 网络失败、限流、无效 ID 等都不应影响整页展示
        logger.warning(f"R18标志：查询 TMDB {tmdbid} 详情失败：{err}")
        return None
    if not isinstance(info, dict):
        return None
    return bool(info.get("adult"))


class R18Marker(_PluginBase):
    """识别结果 R18 标志插件。"""

    plugin_name = "R18标志"
    plugin_desc = "集中展示识别结果并标记 R18（优先用 TMDB 关键词如 hentai=198385），并可一键写入自定义识别词（TMDB 绑定规则）。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.3.0"
    plugin_author = "Ken"
    author_url = "https://github.com/lulu1072502"
    plugin_config_prefix = "r18marker_"
    plugin_order = 50
    auth_level = 1

    _enabled = False
    _source = _SOURCE_ALL
    _count = 10
    _adult_text = "R18"
    _resolve_tmdb = True
    _use_keyword = True
    _hentai_keyword = _DEFAULT_HENTAI_KEYWORD
    _extra_identifiers = ""

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置；按宿主约定允许重复调用。"""
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        source = _text(config.get("source")) or _SOURCE_ALL
        self._source = source if source in _SOURCE_OPTIONS else _SOURCE_ALL
        self._count = _clamp_int(config.get("count"), default=10, low=1, high=_MAX_COUNT)
        self._adult_text = _text(config.get("adult_text")) or "R18"
        self._resolve_tmdb = bool(config.get("resolve_tmdb", True))
        self._use_keyword = bool(config.get("use_keyword", True))
        self._hentai_keyword = _clamp_int(config.get("hentai_keyword_id"), default=_DEFAULT_HENTAI_KEYWORD, low=1, high=10**9)
        self._extra_identifiers = _text(config.get("extra_identifiers")) if config.get("extra_identifiers") else ""
        logger.info(
            "R18标志：配置生效，enabled=%s，来源=%s，每类条数=%s，TMDB判定=%s，关键词判定=%s(%s)",
            self._enabled,
            self._source,
            self._count,
            self._resolve_tmdb,
            self._use_keyword,
            self._hentai_keyword,
        )

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册只读结果接口、R18 判定缓存刷新接口与识别词接口。"""
        return [
            {
                "path": "/results",
                "endpoint": self.api_results,
                "methods": ["GET"],
                "summary": "R18 识别结果",
                "description": "返回当前来源配置下的识别结果清单及其 R18 判定。",
            },
            {
                "path": "/refresh",
                "endpoint": self.api_refresh,
                "methods": ["GET"],
                "summary": "清空 R18 判定缓存",
                "description": "清空成人内容判定缓存，下次展示时重新向数据来源查询。",
            },
            {
                "path": "/identifiers/status",
                "endpoint": self.api_identifiers_status,
                "methods": ["GET"],
                "summary": "识别词同步状态",
                "description": "对比宿主现有自定义识别词与插件内置规则，返回已存在/待写入的条数。",
            },
            {
                "path": "/identifiers/preview",
                "endpoint": self.api_identifiers_preview,
                "methods": ["GET"],
                "summary": "预览识别词合并结果",
                "description": "返回合并后的完整识别词列表（不写入），用于人工确认。",
            },
            {
                "path": "/identifiers/apply",
                "endpoint": self.api_identifiers_apply,
                "methods": ["GET"],
                "summary": "写入识别词（合并）",
                "description": "把插件内置的 TMDB 绑定规则合并写入宿主自定义识别词，已存在的规则不重复添加，不删除用户已有规则。",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回配置页面与默认配置，插件默认开启。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": (
                                                "页面把整理历史、下载历史、订阅里的识别结果集中展示，并标记 R18。判定顺序：TMDB 关键词"
                                                "（默认 198385 hentai）→ TMDB 详情 adult 字段；其它数据源显示「未判定」。"
                                                "内置的 TMDB 绑定规则可在详情页一键合并写入「自定义识别词」。"
                                            ),
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [{"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {"model": "source", "label": "数据来源", "items": list(_SOURCE_OPTIONS)},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {"model": "count", "label": "每类条数", "placeholder": f"1 - {_MAX_COUNT}"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {"model": "adult_text", "label": "标志文字", "placeholder": "R18"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "resolve_tmdb", "label": "调用 TMDB 判定"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "use_keyword", "label": "优先用关键词判定"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "hentai_keyword_id",
                                            "label": "R18 关键词 ID",
                                            "placeholder": str(_DEFAULT_HENTAI_KEYWORD),
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 9},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "extra_identifiers",
                                            "label": "额外识别词（每行一条，写入时追加在内置规则之后）",
                                            "rows": 3,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": True,
            "source": _SOURCE_ALL,
            "count": 10,
            "adult_text": "R18",
            "resolve_tmdb": True,
            "use_keyword": True,
            "hentai_keyword_id": _DEFAULT_HENTAI_KEYWORD,
            "extra_identifiers": "",
        }

    def get_page(self) -> List[dict]:
        """返回详情页：识别结果清单 + R18 标志 + 识别词写入。"""
        if not self._enabled:
            return [_alert("warning", "插件未启用：请在插件配置中开启后查看识别结果。")]

        rows = self._collect_rows()
        page: List[dict] = []
        if not rows:
            page.append(_alert("info", "暂无识别结果：整理历史、下载历史或订阅中还没有匹配的记录。"))
        else:
            r18_rows = [row for row in rows if row.adult is True]
            unknown_rows = [row for row in rows if row.adult is None]
            by_keyword = [row for row in r18_rows if row.r18_source == "keyword"]
            page.append(
                _alert(
                    "info",
                    f"识别结果共 {len(rows)} 条，其中 R18 {len(r18_rows)} 条（关键词命中 {len(by_keyword)} 条），"
                    f"未判定 {len(unknown_rows)} 条。来源范围：{self._source}；每类最多 {self._count} 条。",
                )
            )
            if not self._resolve_tmdb:
                page.append(_alert("warning", "已关闭 TMDB 判定：除宿主自带标记外，其余条目都显示为「未判定」。"))
            page.extend(self._render_row(row) for row in rows)

        # 识别词区块
        status = self._identifiers_status()
        keyword_line = f"（当前用关键词 {self._hentai_keyword}）" if self._use_keyword else "（仅用 adult 字段）"
        if status.get("available"):
            page.append(
                _alert(
                    "success",
                    f"识别词：宿主现有 {status['host_count']} 条，本插件内置 {status['builtin_count']} 条，"
                    f"其中已存在 {status['present']} 条、待写入 {status['missing']} 条{keyword_line}。",
                )
            )
            page.append(self._identifiers_button("/identifiers/preview", "预览合并结果", "info"))
            page.append(self._identifiers_button("/identifiers/apply", "写入识别词（合并，不覆盖已有）", "primary"))
        else:
            page.append(_alert("warning", f"识别词：无法读取宿主配置（{status.get('error') or '未知原因'}）。"))
        page.append(self._refresh_button())
        return page

    def stop_service(self) -> None:
        """停用插件时释放运行状态；进程内 TMDB 客户端由宿主进程自行管理。"""
        self._enabled = False

    # ---------------------------------------------------------------- API

    def api_results(self) -> Any:
        """返回识别结果清单（含 R18 判定），供页面事件或其它调用方使用。"""
        rows = self._collect_rows()
        return {
            "success": True,
            "message": "R18标志：识别结果",
            "source": self._source,
            "count": self._count,
            "total": len(rows),
            "r18": sum(1 for row in rows if row.adult is True),
            "unknown": sum(1 for row in rows if row.adult is None),
            "items": [asdict(row) for row in rows],
        }

    def api_refresh(self) -> Any:
        """清空 R18 判定缓存。"""
        self.save_data(_CACHE_KEY, {})
        logger.info("R18标志：判定缓存已清空")
        return {"success": True, "message": "R18 判定缓存已清空"}

    def api_identifiers_status(self) -> Any:
        """返回识别词同步状态。"""
        return self._identifiers_status()

    def api_identifiers_preview(self) -> Any:
        """返回合并后的识别词（不写入）。"""
        status = self._identifiers_status()
        merged = self._merged_identifiers(status.get("host_list") or [])
        return {
            "success": bool(status.get("available")),
            "message": "R18标志：识别词预览",
            "builtin_count": status.get("builtin_count"),
            "host_count": status.get("host_count"),
            "added": len(merged) - len(status.get("host_list") or []),
            "total": len(merged),
            "head": merged[:8],
            "tail": merged[-8:],
        }

    def api_identifiers_apply(self) -> Any:
        """把内置规则合并写入宿主自定义识别词。"""
        status = self._identifiers_status()
        if not status.get("available"):
            return {"success": False, "message": f"无法读取宿主配置：{status.get('error') or '未知原因'}"}
        host_list = status.get("host_list") or []
        merged = self._merged_identifiers(host_list)
        added = len(merged) - len(host_list)
        if added <= 0:
            return {
                "success": True,
                "message": f"识别词已是最新（宿主 {len(host_list)} 条，无需写入）",
                "added": 0,
                "total": len(host_list),
            }
        ok, err = self._write_host_identifiers(merged)
        if not ok:
            return {"success": False, "message": f"写入识别词失败：{err}"}
        logger.info(f"R18标志：识别词已写入，新增 {added} 条，共 {len(merged)} 条")
        return {
            "success": True,
            "message": f"识别词已写入：新增 {added} 条，共 {len(merged)} 条",
            "added": added,
            "total": len(merged),
        }

    # ------------------------------------------------------------- 识别词

    def _builtin_rules(self) -> List[str]:
        """返回内置规则 + 配置里追加的规则。"""
        rules = [line for line in _BUILTIN_IDENTIFIERS if line.strip()]
        extra = [line.strip() for line in (self._extra_identifiers or "").splitlines() if line.strip()]
        return rules + extra

    def _host_identifiers(self) -> Tuple[Optional[List[str]], Optional[str]]:
        """读取宿主自定义识别词；返回 (列表, 错误信息)。"""
        try:
            from app.application.configuration import get_configured_system_config  # type: ignore
            from app.schemas.types import SystemConfigKey  # type: ignore
        except Exception as err:
            return None, f"导入宿主配置模块失败：{err}"
        try:
            current = get_configured_system_config().get(SystemConfigKey.CustomIdentifiers)
        except Exception as err:
            return None, f"读取自定义识别词失败：{err}"
        return [item for item in (current or []) if isinstance(item, str)], None

    def _write_host_identifiers(self, identifiers: List[str]) -> Tuple[bool, Optional[str]]:
        """写入宿主自定义识别词（走与 /config/identifiers 端点同一配置服务）。"""
        try:
            from app.application.configuration import get_configured_system_config  # type: ignore
            from app.schemas.types import SystemConfigKey  # type: ignore
        except Exception as err:
            return False, f"导入宿主配置模块失败：{err}"
        try:
            get_configured_system_config().set(SystemConfigKey.CustomIdentifiers, identifiers or None)
        except Exception as err:
            return False, str(err)
        return True, None

    def _merged_identifiers(self, host_list: List[str]) -> List[str]:
        """把内置规则合并进宿主已有识别词（保留原顺序，已存在的不重复添加）。"""
        merged = [item for item in host_list if isinstance(item, str)]
        existing = {item.strip() for item in merged}
        for rule in self._builtin_rules():
            if rule.strip() in existing:
                continue
            merged.append(rule)
            existing.add(rule.strip())
        return merged

    def _identifiers_status(self) -> Dict[str, Any]:
        """汇总识别词同步状态。"""
        builtin = self._builtin_rules()
        host_list, err = self._host_identifiers()
        if host_list is None:
            return {"available": False, "error": err, "builtin_count": len(builtin), "host_count": 0}
        host_set = {item.strip() for item in host_list}
        present = sum(1 for rule in builtin if rule.strip() in host_set)
        return {
            "available": True,
            "error": None,
            "builtin_count": len(builtin),
            "host_count": len(host_list),
            "present": present,
            "missing": len(builtin) - present,
            "host_list": host_list,
        }

    # ------------------------------------------------------------- 数据读取

    def _active_sources(self) -> Tuple[str, ...]:
        """返回本次需要读取的来源分组。"""
        if self._source == _SOURCE_ALL:
            return _GROUPED_SOURCES
        if self._source in _GROUPED_SOURCES:
            return (self._source,)
        return ()

    def _collect_rows(self) -> List[_Row]:
        """读取所有目标来源的识别结果。"""
        rows: List[_Row] = []
        for source in self._active_sources():
            try:
                rows.extend(self._query_source(source))
            except Exception as err:  # 单个来源失败不影响其它来源
                logger.error(f"R18标志：读取{source}失败：{err}")
        return rows

    def _query_source(self, source: str) -> List[_Row]:
        """按来源读取一页识别结果。"""
        page = QueryPageRequest(page=1, count=self._count)
        if source == _SOURCE_TRANSFER:
            return [self._row_from_snapshot(source, item) for item in list_transfer_history(page=page).items]
        if source == _SOURCE_DOWNLOAD:
            return [self._row_from_snapshot(source, item) for item in list_download_history(page=page).items]
        if source == _SOURCE_SUBSCRIBE:
            return [self._row_from_snapshot(source, item) for item in list_subscriptions(page=page).items]
        return []

    def _row_from_snapshot(self, source: str, snapshot: Any) -> _Row:
        """把只读快照转换为展示行，并补上 R18 判定。"""
        title = _text(getattr(snapshot, "name", None)) or _text(getattr(snapshot, "title", None))
        media_source = _text(getattr(snapshot, "media_source", None)) or None
        media_id = _text(getattr(snapshot, "media_id", None)) or None
        adult, r18_source = self._r18_of(snapshot, media_source, media_id)
        return _Row(
            source=source,
            title=title or "（无标题）",
            year=_text(getattr(snapshot, "year", None)),
            mtype=_text(getattr(snapshot, "type", None)),
            date=_text(getattr(snapshot, "date", None)),
            media_source=media_source,
            media_id=media_id,
            adult=adult,
            r18_source=r18_source,
        )

    def _r18_of(self, snapshot: Any, media_source: Optional[str], media_id: Optional[str]) -> Tuple[Optional[bool], str]:
        """优先用宿主提供的标记，其次按媒体身份解析。"""
        own = getattr(snapshot, "adult", None)
        if isinstance(own, bool):
            return own, "host"
        mtype = _MEDIA_TYPE_PATH.get(_text(getattr(snapshot, "type", None)), "")
        return self._resolve_r18(media_source, media_id, mtype)

    def _resolve_r18(self, media_source: Optional[str], media_id: Optional[str], mtype: str = "") -> Tuple[Optional[bool], str]:
        """按媒体身份解析 R18，带 TTL 缓存。"""
        if not media_source or not media_id:
            return None, "none"
        cache_key = f"{media_source}:{media_id}"
        cache = self._adult_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            try:
                fresh = time.time() - float(cached.get("ts") or 0) < _ADULT_TTL_SECONDS
            except (TypeError, ValueError):
                fresh = False
            if fresh and (isinstance(cached.get("adult"), bool) or cached.get("adult") is None):
                return cached.get("adult"), _text(cached.get("src")) or "none"

        if not self._resolve_tmdb or media_source != _TMDB_SOURCE:
            return None, "none"

        # 1) 关键词判定
        if self._use_keyword:
            keywords = _fetch_tmdb_keywords(media_id, mtype)
            if keywords is not None:
                hit = self._hentai_keyword in keywords
                self._store_r18(cache_key, hit, "keyword")
                return hit, "keyword"

        # 2) 回退 adult 字段
        adult = _fetch_tmdb_adult(media_id)
        if adult is not None:
            self._store_r18(cache_key, adult, "adult")
        return adult, "adult" if adult is not None else "none"

    def _adult_cache(self) -> Dict[str, Any]:
        """读取判定缓存，异常或脏数据时回退为空缓存。"""
        cache = self.get_data(_CACHE_KEY)
        return cache if isinstance(cache, dict) else {}

    def _store_r18(self, cache_key: str, adult: bool, source: str) -> None:
        """写入判定缓存并按上限裁剪。"""
        cache = self._adult_cache()
        cache[cache_key] = {"adult": bool(adult), "src": source, "ts": time.time()}
        if len(cache) > _ADULT_CACHE_LIMIT:
            ordered = sorted(
                cache.items(),
                key=lambda item: float(item[1].get("ts") or 0) if isinstance(item[1], dict) else 0.0,
            )
            cache = dict(ordered[-_ADULT_CACHE_LIMIT:])
        try:
            self.save_data(_CACHE_KEY, cache)
        except Exception as err:
            logger.warning(f"R18标志：写入判定缓存失败：{err}")

    # ------------------------------------------------------------- 页面渲染

    def _render_row(self, row: _Row) -> dict:
        """渲染一行识别结果，成人条目显示 R18 徽标。"""
        parts = [f"{row.title}（{row.year}）" if row.year else row.title]
        if row.mtype:
            parts.append(row.mtype)
        parts.append(row.source)
        if row.media_source and row.media_id:
            parts.append(f"{row.media_source}:{row.media_id}")
        if row.date:
            parts.append(row.date)

        if row.adult is True:
            label = self._adult_text if row.r18_source == "keyword" else f"{self._adult_text}"
            badge = _chip("error", "flat", label)
        elif row.adult is None:
            badge = _chip("warning", "tonal", f"{self._adult_text} 未判定")
        else:
            badge = _chip("success", "tonal", "非 R18")

        return {
            "component": "VCard",
            "props": {"variant": "tonal", "class": "mb-2"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "VRow",
                            "props": {"align": "center"},
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 9},
                                    "content": [
                                        {
                                            "component": "VCardText",
                                            "props": {"class": "pa-0 text-body-2"},
                                            "text": " · ".join(parts),
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 3, "class": "d-flex justify-end"},
                                    "content": [badge],
                                },
                            ],
                        }
                    ],
                }
            ],
        }

    def _refresh_button(self) -> dict:
        """返回「重新判定」按钮：调用插件 API 并触发页面重新加载。"""
        return self._identifiers_button("/refresh", "清空判定缓存并重新判定", "secondary")

    def _identifiers_button(self, path: str, text: str, color: str) -> dict:
        """构造一个调用插件 API 的按钮（点击后前端会重新拉取页面数据）。"""
        return {
            "component": "VBtn",
            "props": {"color": color, "variant": "tonal", "class": "mt-2 mr-2"},
            "text": text,
            "events": {
                "@click": {
                    "api": f"plugin/{self.__class__.__name__}{path}",
                    "method": "GET",
                    "params": {},
                }
            },
        }


def _alert(alert_type: str, text: str) -> dict:
    """构造 VAlert 页面节点。"""
    return {"component": "VAlert", "props": {"type": alert_type, "variant": "tonal", "text": text}}


def _chip(color: str, variant: str, text: str) -> dict:
    """构造 VChip 徽标节点。"""
    return {"component": "VChip", "props": {"color": color, "variant": variant, "size": "small"}, "text": text}
