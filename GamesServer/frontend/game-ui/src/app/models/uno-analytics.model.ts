export interface GameSummary {
  game_id: string;
  started_at: string | null;
  ended_at: string | null;
  max_players: number;
  winner_player: number | null;
  total_turns: number;
}

export interface GameEvent {
  ts: string;
  player_id?: number | null;
  player_name?: string | null;
  event_type: string;
  card?: string | null;
  extra?: any;
}


export interface AnalysisRequest {
  question: string;
}

export interface AnalysisResponse {
  game_id: string;
  question: string;
  analysis: string;
}

export interface AnalysisIA {
  question: string;
  answer: string;
  model: string;
  created_at: string;
}

export interface GameDetails {
  game_id: string;
  started_at: string | null;
  ended_at: string | null;
  max_players: number;
  winner_player: number | null;
  total_turns: number;
  events: GameEvent[];
  analyses: AnalysisIA[];
}
