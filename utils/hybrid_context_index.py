"""Hybrid-mode translation context: keyword overlap via inverted index."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import AbstractSet, Iterable, Mapping, Sequence

_TOKEN_RE = re.compile(r"[a-zA-Z]+")

_HYBRID_EN_STOPWORDS_RAW = (
    "able ableabout about above abroad abst accordance according accordingly across act actually ad added "
    "adj adopted ae af affected affecting affects after afterwards ag again against ago ah "
    "ahead ai aint al all allow allows almost alone along alongside already also although "
    "always am amid amidst among amongst amoungst amount an and announce another any anybody "
    "anyhow anymore anyone anything anyway anyways anywhere ao apart apparently appear appreciate appropriate approximately "
    "aq ar are area areas aren arent arise around arpa as aside ask asked "
    "asking asks associated at au auth available aw away awfully az ba back backed "
    "backing backs backward backwards bb bd be became because become becomes becoming been before "
    "beforehand began begin beginning beginnings begins behind being beings believe below beside besides best "
    "better between beyond bf bg bh bi big bill billion biol bj bm bn "
    "bo both bottom br brief briefly bs bt but buy bv bw by bz "
    "ca call came can cannot cant caption case cases cause causes cc cd certain "
    "certainly cf cg ch changes ci ck cl clear clearly click cm cmon cn "
    "co com come comes computer con concerning consequently consider considering contain containing contains copy "
    "corresponding could couldn couldnt course cr cry cs cu currently cv cx cy cz "
    "dare darent date de dear definitely describe described despite detail did didn didnt differ "
    "different differently directly dj dk dm do does doesn doesnt doing don done dont "
    "doubtful down downed downing downs downwards due during dz each early ec ed edu "
    "ee effect eg eh eight eighty either eleven else elsewhere empty end ended ending "
    "ends enough entirely er es especially et etc even evenly ever evermore every everybody "
    "everyone everything everywhere ex exactly example except face faces fact facts fairly far farther "
    "felt few fewer ff fi fifteen fifth fifty fify fill find finds fire first "
    "five fix fj fk fm fo followed following follows for forever former formerly forth "
    "forty forward found four fr free from front full fully further furthered furthering furthermore "
    "furthers fx ga gave gb gd ge general generally get gets getting gf gg "
    "gh gi give given gives giving gl gm gmt gn go goes going gone "
    "good goods got gotten gov gp gq gr great greater greatest greetings group grouped "
    "grouping groups gs gt gu gw gy had hadnt half happens hardly has hasn "
    "hasnt have haven havent having he hed hell hello help hence her here hereafter "
    "hereby herein heres hereupon hers herself hes hi hid high higher highest him himself "
    "his hither hk hm hn home homepage hopefully how howbeit however hr ht htm "
    "html http hu hundred id ie if ignored ii il ill im immediate immediately "
    "importance important in inasmuch inc indeed index indicate indicated indicates information inner inside insofar "
    "instead int interest interested interesting interests into invention inward io iq ir is isn "
    "isnt it itd itll its itself ive je jm jo join jp just ke "
    "keep keeps kept keys kg kh ki kind km kn knew know known knows "
    "kp kr kw ky kz la large largely last lately later latest latter latterly "
    "lb lc least length less lest let lets li like liked likely likewise line "
    "little lk ll long longer longest look looking looks low lower lr ls lt "
    "ltd lu lv ly ma made mainly make makes making man many may maybe "
    "maynt mc md me mean means meantime meanwhile member members men merely mg mh "
    "microsoft might mightnt mil mill million mine minus miss mk ml mm mn mo "
    "more moreover most mostly move mp mq mr mrs ms msie mt mu much "
    "mug must mustnt mv mw mx my myself mz na name namely nay nc "
    "nd ne near nearly necessarily necessary need needed needing neednt needs neither net netscape "
    "never neverf neverless nevertheless new newer newest next nf ng ni nine ninety nl "
    "no nobody non none nonetheless noone nor normally nos not noted nothing notwithstanding novel "
    "now nowhere np nr nu null number numbers nz obtain obtained obviously of off "
    "often oh ok okay old older oldest om omitted on once one ones only "
    "onto open opened opening opens opposite or ord order ordered ordering orders org other "
    "others otherwise ought oughtnt our ours ourselves out outside over overall owing own pa "
    "page pages part parted particular particularly parting parts past pe per perhaps pf pg "
    "ph pk pl place placed places please plus pm pmid pn point pointed pointing "
    "points poorly possible possibly potentially pp pr predominantly present presented presenting presents presumably previously "
    "primarily probably problem problems promptly proud provided provides pt put puts pw py qa "
    "que quickly quite qv ran rather rd re readily really reasonably recent recently ref "
    "refs regarding regardless regards related relatively research reserved respectively resulted resulting results right ring "
    "ro room rooms round ru run rw sa said same saw say saying says "
    "sb sc sd se sec second secondly seconds section see seeing seem seemed seeming "
    "seems seen sees self selves sensible sent serious seriously seven seventy several sg sh "
    "shall shant she shed shell shes should shouldn shouldnt show showed showing shown showns "
    "shows si side sides significant significantly similar similarly since sincere site six sixty sj "
    "sk sl slightly sm small smaller smallest sn so some somebody someday somehow someone "
    "somethan something sometime sometimes somewhat somewhere soon sorry specifically specified specify specifying sr st "
    "state states still stop strongly su sub substantially successfully such sufficiently suggest sup sure "
    "sv sy system sz take taken taking tc td tell ten tends test text "
    "tf tg th than thank thanks thanx that thatll thats thatve the their theirs "
    "them themselves then thence there thereafter thereby thered therefore therein therell thereof therere theres "
    "thereto thereupon thereve these they theyd theyll theyre theyve thick thin thing things think "
    "thinks third thirty this thorough thoroughly those thou though thoughh thought thoughts thousand three "
    "throug through throughout thru thus til till tip tis tj tk tm tn to "
    "today together too took top toward towards tp tr tried tries trillion truly try "
    "trying ts tt turn turned turning turns tv tw twas twelve twenty twice two "
    "tz ua ug uk um un under underneath undoing unfortunately unless unlike unlikely until "
    "unto up upon ups upwards us use used useful usefully usefulness uses using usually "
    "uucp uy uz va value various vc ve versus very vg vi via viz "
    "vn vol vols vs vu want wanted wanting wants was wasn wasnt way ways "
    "we web webpage website wed welcome well wells went were weren werent weve wf "
    "what whatever whatll whats whatve when whence whenever where whereafter whereas whereby wherein wheres "
    "whereupon wherever whether which whichever while whilst whim whither who whod whoever whole wholl "
    "whom whomever whos whose why widely width will willing wish with within without won "
    "wonder wont words work worked working works world would wouldn wouldnt ws www ye "
    "year years yes yet you youd youll young younger youngest your youre yours yourself "
    "yourselves youve yt yu za zero zm zr "
)

HYBRID_EN_STOPWORDS: frozenset[str] = frozenset(w.lower() for w in _HYBRID_EN_STOPWORDS_RAW.split() if w)


class HybridContextIndex:
    """Content-word -> translated English keys, for O(batch + hits) context lookup."""

    __slots__ = ("_postings", "_en_tokens", "_en_to_zh", "_stopwords")

    def __init__(
        self,
        translated_texts: Mapping[str, Sequence[str]],
        stopwords: frozenset[str] | None = None,
    ) -> None:
        self._stopwords = stopwords if stopwords is not None else HYBRID_EN_STOPWORDS
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._en_tokens: dict[str, frozenset[str]] = {}
        self._en_to_zh: dict[str, list[str]] = {
            en: list(zhs) for en, zhs in translated_texts.items() if zhs
        }

        for en in self._en_to_zh:
            toks = frozenset(
                t
                for t in _TOKEN_RE.findall(en.lower())
                if len(t) >= 2 and t not in self._stopwords
            )
            self._en_tokens[en] = toks
            for w in toks:
                self._postings[w].add(en)

    def build_context(
        self,
        batch_english_lines: Iterable[str],
        pending_english: AbstractSet[str],
        *,
        max_lines: int = 50,
    ) -> str:
        batch_words: set[str] = set()
        for line in batch_english_lines:
            for t in _TOKEN_RE.findall((line or "").lower()):
                if len(t) >= 2 and t not in self._stopwords:
                    batch_words.add(t)

        if not batch_words:
            return ""

        candidates: set[str] = set()
        for w in batch_words:
            candidates |= self._postings.get(w, set())

        candidates -= pending_english
        if not candidates:
            return ""

        def rank_key(en: str) -> tuple[int, int]:
            overlap = len(self._en_tokens.get(en, frozenset()) & batch_words)
            return overlap, -len(en)

        ordered = sorted(candidates, key=rank_key, reverse=True)

        lines: list[str] = []
        for en in ordered:
            if len(lines) >= max_lines:
                break
            for zh in self._en_to_zh.get(en, ()):
                if len(lines) >= max_lines:
                    break
                lines.append(f"关联文本参考: {en} -> {zh}")

        logging.debug(
            "混合模式上下文: 批次关键词 %d 个, 候选已译句 %d 条, 写入提示 %d 行",
            len(batch_words),
            len(candidates),
            len(lines),
        )
        return "\n".join(lines)
