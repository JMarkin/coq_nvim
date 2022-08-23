from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import AbstractSet, Literal, Mapping, Optional, Tuple, Union

from pynvim_pp.float_win import Border


@dataclass(frozen=True)
class Limits:
    idle_timeout: float
    index_cutoff: int
    completion_auto_timeout: float
    completion_manual_timeout: float
    download_retries: int
    download_timeout: float


@dataclass(frozen=True)
class GhostText:
    enabled: bool
    context: Tuple[str, str]
    highlight_group: str


@dataclass(frozen=True)
class PumDisplay:
    fast_close: bool

    y_ratio: float
    y_max_len: int

    x_max_len: int
    x_truncate_len: int

    ellipsis: str

    kind_context: Tuple[str, str]
    source_context: Tuple[str, str]


@dataclass(frozen=True)
class PreviewPositions:
    north: Optional[int]
    south: Optional[int]
    west: Optional[int]
    east: Optional[int]


@dataclass(frozen=True)
class PreviewDisplay:
    x_max_len: int
    positions: PreviewPositions
    border: Border
    resolve_timeout: float


class IconMode(Enum):
    none = auto()
    short = auto()
    long = auto()


@dataclass(frozen=True)
class Icons:
    mode: IconMode
    spacing: int
    aliases: Mapping[str, str]
    mappings: Mapping[str, str]


@dataclass(frozen=True)
class Display:
    ghost_text: GhostText
    pum: PumDisplay
    preview: PreviewDisplay
    icons: Icons
    time_fmt: str
    mark_highlight_group: str


@dataclass(frozen=True)
class MatchOptions:
    unifying_chars: AbstractSet[str]
    max_results: int
    proximate_lines: int
    look_ahead: int
    exact_matches: int
    fuzzy_cutoff: float


@dataclass(frozen=True)
class Weights:
    prefix_matches: float
    edit_distance: float
    recency: float
    proximity: float


@dataclass(frozen=True)
class CompleteOptions:
    always: bool
    smart: bool
    replace_prefix_threshold: int
    skip_after: AbstractSet[str]


@dataclass(frozen=True)
class KeyMapping:
    recommended: bool
    pre_select: bool
    manual_complete: Optional[str]
    repeat: Optional[str]
    jump_to_mark: Optional[str]
    bigger_preview: Optional[str]
    eval_snips: Optional[str]
    manual_complete_insertion_only: Optional[bool]


@dataclass(frozen=True)
class _AlwaysTop:
    always_on_top: bool


@dataclass(frozen=True)
class _AlwaysTops:
    always_on_top: Optional[AbstractSet[Optional[str]]]


@dataclass(frozen=True)
class BaseClient:
    enabled: bool
    short_name: str
    weight_adjust: float


@dataclass(frozen=True)
class _WordbankClient(BaseClient):
    match_syms: bool


class PathResolution(Enum):
    cwd = auto()
    file = auto()


@dataclass(frozen=True)
class PathsClient(BaseClient, _AlwaysTop):
    resolution: AbstractSet[PathResolution]
    preview_lines: int
    path_seps: AbstractSet[str]


@dataclass(frozen=True)
class BuffersClient(_WordbankClient, _AlwaysTop):
    same_filetype: bool
    parent_scope: str


@dataclass(frozen=True)
class TagsClient(BaseClient, _AlwaysTop):
    parent_scope: str
    path_sep: str


@dataclass(frozen=True)
class TmuxClient(_WordbankClient, TagsClient, _AlwaysTop):
    all_sessions: bool


@dataclass(frozen=True)
class TSClient(BaseClient, _AlwaysTop):
    path_sep: str
    search_context: int
    slow_threshold: float


@dataclass(frozen=True)
class T9Client(BaseClient, _AlwaysTop):
    ...


class SnippetWarnings(Enum):
    missing = auto()
    outdated = auto()


@dataclass(frozen=True)
class SnippetClient(BaseClient, _AlwaysTop):
    user_path: Optional[Path]
    warn: AbstractSet[SnippetWarnings]


@dataclass(frozen=True)
class LSPClient(BaseClient, _AlwaysTops):
    resolve_timeout: float


@dataclass(frozen=True)
class ThirdPartyClient(BaseClient, _AlwaysTops):
    ...


@dataclass(frozen=True)
class Clients:
    buffers: BuffersClient
    lsp: LSPClient
    paths: PathsClient
    snippets: SnippetClient
    tabnine: T9Client
    tags: TagsClient
    third_party: ThirdPartyClient
    tmux: TmuxClient
    tree_sitter: TSClient


@dataclass(frozen=True)
class Settings:
    auto_start: Union[bool, Literal["shut-up"]]
    xdg: bool
    limits: Limits
    display: Display
    match: MatchOptions
    weights: Weights
    completion: CompleteOptions
    keymap: KeyMapping
    clients: Clients
