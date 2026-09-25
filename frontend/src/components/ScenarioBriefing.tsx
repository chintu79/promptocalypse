import { useEffect, useState } from 'react';
import './ScenarioBriefing.css';
import { fetchScenario, type ScenarioData } from '../api/client';

interface ScenarioBriefingProps {
  currentLevel: number;
}

export default function ScenarioBriefing({ currentLevel }: ScenarioBriefingProps) {
  const [glitch, setGlitch] = useState(false);
  const [data, setData] = useState<ScenarioData | null>(null);

  useEffect(() => {
    setGlitch(true);
    fetchScenario(currentLevel)
      .then(setData)
      .catch(console.error)
      .finally(() => {
        setTimeout(() => setGlitch(false), 500);
      });
  }, [currentLevel]);

  return (
    <div className={`scenario-briefing ${glitch ? 'glitch-effect' : ''}`}>
      <h3>MISSION BRIEFING - LEVEL {currentLevel}</h3>
      {data ? (
        <ul>
          <li><strong>Target:</strong> {data.target}</li>
          <li><strong>Scenario:</strong> {data.scenario}</li>
          <li><strong>Attack Vector:</strong> {data.attack_vector}</li>
        </ul>
      ) : (
        <p>Loading scenario data...</p>
      )}
    </div>
  );
}
