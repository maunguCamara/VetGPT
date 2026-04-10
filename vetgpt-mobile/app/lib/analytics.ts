interface AnalyticsEvent {
  event: string;
  properties: Record<string, any>;
  timestamp: number;
}

class Analytics {
  private events: AnalyticsEvent[] = [];
  
  trackQuery(query: string, latency_ms: number, model: string, offline: boolean) {
    this.events.push({
      event: 'query',
      properties: {
        query_length: query.length,
        latency_ms,
        model,
        offline,
        timestamp: new Date().toISOString()
      },
      timestamp: Date.now()
    });
  }
  
  trackModelPerformance(engine: string, tokens_per_sec: number, memory_mb: number) {
    this.events.push({
      event: 'model_performance',
      properties: { engine, tokens_per_sec, memory_mb },
      timestamp: Date.now()
    });
  }
  
  async flush() {
    // Send to backend
    if (this.events.length > 0) {
      await fetch('/api/analytics', {
        method: 'POST',
        body: JSON.stringify({ events: this.events })
      });
      this.events = [];
    }
  }
}

export const analytics = new Analytics();