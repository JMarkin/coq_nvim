from itertools import chain
from locale import strxfrm
from os import linesep
from string import Template
from typing import Iterable, Iterator, Mapping, Sequence, Tuple
from uuid import uuid4

from pynvim_pp.buffer import Buffer
from pynvim_pp.float_win import list_floatwins, open_float_win
from pynvim_pp.lib import display_width
from std2.locale import si_prefixed_smol

from ...consts import MD_STATS
from ...databases.insertions.database import Statistics
from ...lang import LANG
from ...registry import rpc
from ..rt_types import Stack

_TAB_SIZE = 2
_H_SEP = " | "
_V_SEP = "─"

_TPL = f"""
# {LANG("statistics")}

${{chart1}}

${{chart2}}

${{chart3}}

${{desc}}
""".lstrip()

_NS = uuid4()


def _table(headers: Sequence[str], rows: Mapping[str, Mapping[str, str]]) -> str:
    s_rows = sorted(rows.keys(), key=strxfrm)
    c0_just = max(
        chain((0,), (display_width(key, tabsize=_TAB_SIZE) for key in s_rows))
    )
    c_justs = {
        header: max(
            chain(
                (display_width(header, tabsize=_TAB_SIZE),),
                (
                    display_width(vs.get(header, ""), tabsize=_TAB_SIZE)
                    for vs in rows.values()
                ),
            )
        )
        for header in headers
    }

    def cont() -> Iterator[str]:
        yield _H_SEP.join(
            chain(
                (" " * c0_just,), (header.ljust(c_justs[header]) for header in headers)
            )
        )
        for key in s_rows:
            yield _H_SEP.join(
                chain(
                    (key.ljust(c0_just),),
                    (
                        rows[key].get(header, "").ljust(c_justs[header])
                        for header in headers
                    ),
                )
            )

    h, *t = cont()
    rep = display_width(h, tabsize=_TAB_SIZE)
    sep = f"{linesep}{_V_SEP * rep}{linesep}"
    return sep.join(chain((h,), t))


def _trans(stat: Statistics) -> Iterator[Tuple[str, Mapping[str, str]]]:
    stat.interrupted
    m1 = {
        "Interrupted": str(stat.interrupted),
        "Inserted": str(stat.inserted),
    }
    yield stat.source, m1

    m2 = {
        "Avg Duration": f"{si_prefixed_smol(stat.avg_duration, precision=0)}s",
        "Q10 Duration": f"{si_prefixed_smol(stat.q10_duration, precision=0)}s",
        "Q50 Duration": f"{si_prefixed_smol(stat.q50_duration, precision=0)}s",
        "Q95 Duration": f"{si_prefixed_smol(stat.q95_duration, precision=0)}s",
        "Q99 Duration": f"{si_prefixed_smol(stat.q99_duration, precision=0)}s",
    }
    yield stat.source, m2

    m3 = {
        "Avg Items": str(round(stat.avg_items)),
        "Q50 Items": str(stat.q50_items),
        "Q99 Items": str(stat.q99_items),
    }
    yield stat.source, m3


def _pprn(stats: Iterable[Statistics]) -> Iterator[str]:
    if not stats:
        yield from ("", "", "")
    else:
        for acc in zip(*map(_trans, stats)):
            rows = {k: v for k, v in acc}
            headers = tuple(key for key, _ in next(iter(rows.values()), {}).items())
            table = _table(headers, rows=rows)
            yield table


@rpc()
async def stats(stack: Stack, *_: str) -> None:
    stats = stack.idb.stats()
    chart1, chart2, chart3 = _pprn(stats)
    desc = MD_STATS.read_text()
    lines = (
        Template(_TPL)
        .substitute(chart1=chart1, chart2=chart2, chart3=chart3, desc=desc)
        .splitlines()
    )
    async for win in list_floatwins(_NS):
        await win.close()
    buf = await Buffer.create(
        listed=False, scratch=True, wipe=True, nofile=True, noswap=True
    )
    await buf.set_lines(lines)
    await buf.opts.set("modifiable", val=False)
    await buf.opts.set("syntax", val="markdown")
    await open_float_win(_NS, margin=0, relsize=0.95, buf=buf, border="rounded")
