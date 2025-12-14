SELECT question, answer, model, created_at
FROM game_analysis
WHERE game_id = 'df110fdd'
ORDER BY created_at DESC
