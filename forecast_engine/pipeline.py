"""Lazy, reusable Chronos pipeline loading and inference serialization."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Iterator

import torch
from chronos import BaseChronosPipeline

from .models import ModelSpec


PipelineLoader = Callable[..., Any]


def _default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _default_dtype(device: str) -> str:
    return "bfloat16" if device.startswith("cuda") else "float32"


def _load_pipeline(
    model_id: str,
    *,
    device: str,
    dtype: str,
    revision: str | None,
) -> Any:
    kwargs: dict[str, Any] = {
        "device_map": device,
        "dtype": dtype,
    }
    if revision:
        kwargs["revision"] = revision
    return BaseChronosPipeline.from_pretrained(model_id, **kwargs)


@dataclass(frozen=True)
class PipelineKey:
    """Properties that affect the loaded model weights/runtime."""

    model_id: str
    device: str
    dtype: str
    revision: str | None


@dataclass
class _PipelineHandle:
    pipeline: Any
    lock: RLock = field(default_factory=RLock)
    model_names: set[str] = field(default_factory=set)


class PipelineManager:
    """Load each configured model/runtime combination once and reuse it."""

    def __init__(
        self,
        *,
        device: str | None = None,
        dtype: str | None = None,
        revision: str | None = None,
        loader: PipelineLoader | None = None,
    ) -> None:
        self.device = device or _default_device()
        self.dtype = dtype or _default_dtype(self.device)
        self.revision = revision
        self._loader = loader or _load_pipeline
        self._cache: dict[PipelineKey, _PipelineHandle] = {}
        self._cache_lock = RLock()

    @contextmanager
    def pipeline(self, spec: ModelSpec) -> Iterator[Any]:
        """Yield a loaded pipeline while serializing inference on that pipeline."""
        key = PipelineKey(
            model_id=spec.model_id,
            device=self.device,
            dtype=self.dtype,
            revision=self.revision,
        )
        with self._cache_lock:
            handle = self._cache.get(key)
            if handle is None:
                pipeline = self._loader(
                    spec.model_id,
                    device=self.device,
                    dtype=self.dtype,
                    revision=self.revision,
                )
                handle = _PipelineHandle(pipeline=pipeline)
                self._cache[key] = handle
            handle.model_names.add(spec.name)

        with handle.lock:
            yield handle.pipeline

    @property
    def cached_pipeline_count(self) -> int:
        """Number of loaded pipeline instances without triggering a load."""
        with self._cache_lock:
            return len(self._cache)

    @property
    def loaded_models(self) -> list[str]:
        """Model names represented by loaded pipeline instances."""
        with self._cache_lock:
            model_names: set[str] = set()
            for handle in self._cache.values():
                model_names.update(handle.model_names)
            return sorted(model_names)
