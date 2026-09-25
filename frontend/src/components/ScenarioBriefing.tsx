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
    <div className={`scenario-briefing-banner ${glitch ? 'glitch-effect' : ''}`}>
      {data ? (
        <span>
          <strong>[LEVEL {currentLevel}]</strong> TARGET: {data.target} // VECTOR: {data.attack_vector} // {data.scenario}
        </span>
      ) : (
        <span>
          <strong>[LEVEL {currentLevel}]</strong> Loading scenario data...
        </span>
      )}
    </div>
  );
}
