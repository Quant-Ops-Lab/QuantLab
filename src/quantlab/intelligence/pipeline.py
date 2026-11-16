"""News/facts pipeline is independent from model inference and execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .events import EventFact,EventJournal

class EventSource(Protocol):
    def collect(self)->list[EventFact]: ...

class EventSink(Protocol):
    def publish(self, topic:str,payload:dict)->None: ...

@dataclass(frozen=True)
class IngestResult:
    seen:int
    inserted:int
    errors:tuple[str,...]

class IntelligencePipeline:
    def __init__(self, sources:list[EventSource],journal:EventJournal,sink:EventSink|None=None):
        self.sources=sources
        self.journal=journal
        self.sink=sink

    def cycle(self)->IngestResult:
        seen=inserted=0
        errors=[]
        for src in self.sources:
            try:
                batch=src.collect()
                for event in batch:
                    seen+=1
                    if self.journal.append(event):
                        inserted+=1
                        if self.sink:
                            try:self.sink.publish('quantlab/intelligence/event',event.to_dict())
                            except Exception as e: errors.append('publish:'+type(e).__name__)
            except Exception as e:
                errors.append(type(src).__name__+':'+type(e).__name__)
        return IngestResult(seen,inserted,tuple(errors))
