from typing import MutableSequence, Optional

from pynvim import Nvim

from ...shared.types import ExternLSP, ExternLUA
from ..parse import parse_item
from ..types import Completion
from .request import async_request


async def resolve(nvim: Nvim, extern: ExternLSP) -> Optional[Completion]:
    name = "lsp_third_party_resolve" if isinstance(extern, ExternLUA) else "lsp_resolve"
    comps: MutableSequence[Completion] = []

    clients = {extern.client} if extern.client else set()
    async for client, resp in async_request(nvim, name, clients, extern.item):
        comp = parse_item(
            type(extern),
            client=client,
            short_name="",
            always_on_top=None,
            weight_adjust=0,
            item=resp,
        )
        if extern.client and client == extern.client:
            return comp
        elif comp:
            comps.append(comp)
    else:
        for comp in comps:
            if comp.doc:
                return comp
        else:
            return None
