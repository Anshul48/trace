import asyncio
import time
from typing import Dict, List
from sentence_transformers import CrossEncoder
from trace.core.db import db
from trace.events.bus import event_bus, Event

class AttentionDaemon:
    def __init__(self):
        # Local Cross-Encoder for scoring
        self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        # In-memory cache mapping project_id -> { trace_id: score }
        self.attention_scores: Dict[str, Dict[str, float]] = {}
        # Cooldown tracker mapping project_id -> last_trigger_timestamp
        self.last_trigger: Dict[str, float] = {}

    def _score_trace(self, goal: str, raw_text: str, summary: str) -> float:
        # CrossEncoder expects pairs: [query, document]
        pairs = [
            [goal, raw_text or ""],
            [goal, summary or ""]
        ]
        try:
            scores = self.model.predict(pairs)
            # The model outputs logits, we can apply a simple sigmoid or just use the logits.
            # ms-marco-MiniLM-L-6-v2 outputs can range from roughly -10 to +10.
            # We'll just take the max logit.
            max_score = float(max(scores))
            # Convert to a pseudo-probability 0-1 (sigmoid)
            import math
            return 1 / (1 + math.exp(-max_score))
        except Exception as e:
            print(f"AttentionDaemon scoring error: {e}")
            return 0.0

    async def _sweep_project(self, project_id: str, goal: str):
        if project_id not in self.attention_scores:
            self.attention_scores[project_id] = {}
            
        traces = db.get_traces_by_project(project_id)
        for trace in traces:
            trace_id = trace['trace_id']
            if trace_id not in self.attention_scores[project_id]:
                score = self._score_trace(goal, trace.get('raw_source_text', ''), trace.get('summary_trace', ''))
                self.attention_scores[project_id][trace_id] = score

    async def _on_goal_updated(self, event: Event):
        payload = event.payload
        if isinstance(payload, dict):
            project_id = payload.get("project_id")
            goal = payload.get("goal")
        else:
            project_id = getattr(payload, "project_id", None)
            goal = getattr(payload, "goal", None)

        if project_id and goal:
            # Clear old cache for this project and sweep
            self.attention_scores[project_id] = {}
            asyncio.create_task(self._sweep_project(project_id, goal))

    async def _on_trace_extracted(self, event: Event):
        # Score the new trace immediately if there's an active goal
        payload = event.payload
        if isinstance(payload, dict):
            project_id = payload.get("project_id")
            trace_id = payload.get("trace_id")
            raw_source = payload.get("raw_source_text", "")
            summary = payload.get("summary_trace", "")
        else:
            project_id = getattr(payload, "project_id", None)
            trace_id = getattr(payload, "trace_id", None)
            raw_source = getattr(payload, "raw_source_text", "")
            summary = getattr(payload, "summary_trace", "")

        if project_id and trace_id:
            goal = db.get_project_goal(project_id)
            if goal:
                if project_id not in self.attention_scores:
                    self.attention_scores[project_id] = {}
                score = self._score_trace(goal, raw_source, summary)
                self.attention_scores[project_id][trace_id] = score

    async def start(self):
        # Subscribe to events
        event_bus.subscribe("GoalUpdated", self._on_goal_updated)
        event_bus.subscribe("TraceExtracted", self._on_trace_extracted)

        # Initial sweep for any projects that already have goals
        projects = db.get_all_projects()
        for p in projects:
            goal = db.get_project_goal(p['id'])
            if goal:
                await self._sweep_project(p['id'], goal)

        # Consolidation Loop
        while True:
            await asyncio.sleep(60)
            now = time.time()
            for project_id, scores in self.attention_scores.items():
                goal = db.get_project_goal(project_id)
                if not goal:
                    continue
                    
                # Threshold logic: sum of scores > 0.85 should exceed 4.0 (approx 5 highly relevant traces)
                high_scoring_traces = [tid for tid, score in scores.items() if score > 0.85]
                total_high_score = sum(scores[tid] for tid in high_scoring_traces)
                
                if total_high_score > 4.0:
                    last_time = self.last_trigger.get(project_id, 0)
                    # 5-minute cooldown to prevent spamming
                    if now - last_time > 300:
                        self.last_trigger[project_id] = now
                        await event_bus.publish(Event(
                            name="AutoResearchTriggered",
                            payload={
                                "project_id": project_id,
                                "goal": goal,
                                "trace_ids": high_scoring_traces
                            }
                        ))

# Global daemon instance
attention_daemon = AttentionDaemon()
