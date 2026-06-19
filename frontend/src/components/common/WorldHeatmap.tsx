import { useMemo } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';

import type { HeatmapData } from '@/utils/types';

// world-atlas country boundaries (TopoJSON) fetched at runtime.
const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

// Map our country names to the TopoJSON's names where they differ.
const NAME_ALIASES: Record<string, string> = {
  'United States': 'United States of America',
  'Czech Republic': 'Czechia',
  'Dominican Republic': 'Dominican Rep.',
  'Bosnia and Herzegovina': 'Bosnia and Herz.',
  "Côte d'Ivoire": "Côte d'Ivoire",
  'South Korea': 'South Korea',
};

const normalize = (name: string) => (NAME_ALIASES[name] ?? name).toLowerCase();

interface WorldHeatmapProps {
  data: HeatmapData[];
}

const WorldHeatmap = ({ data }: WorldHeatmapProps) => {
  const { counts, max } = useMemo(() => {
    const tally: Record<string, number> = {};
    for (const row of data) {
      if (!row.country) {
        continue;
      }
      const key = normalize(row.country);
      tally[key] = (tally[key] ?? 0) + row.count;
    }
    return { counts: tally, max: Object.values(tally).reduce((acc, value) => Math.max(acc, value), 0) };
  }, [data]);

  const fillFor = (geoName: string) => {
    const count = counts[geoName.toLowerCase()] ?? 0;
    if (count <= 0 || max <= 0) {
      return '#F1F5F9';
    }
    return `rgba(37, 99, 235, ${(0.25 + 0.75 * (count / max)).toFixed(3)})`;
  };

  return (
    <div className="h-80">
      <ComposableMap projectionConfig={{ scale: 135 }} height={330} style={{ width: '100%', height: '100%' }}>
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const name = (geo.properties as { name?: string }).name ?? '';
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fillFor(name)}
                  stroke="#E2E8F0"
                  strokeWidth={0.4}
                  style={{
                    default: { outline: 'none' },
                    hover: { outline: 'none', fill: '#1D4ED8' },
                    pressed: { outline: 'none' },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>
    </div>
  );
};

export default WorldHeatmap;
