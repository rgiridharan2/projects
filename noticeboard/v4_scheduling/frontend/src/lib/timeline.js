// Layout maths for the agenda's hourly timeline. Pure functions, no React.

const DEFAULT_START_HOUR = 8;
const DEFAULT_END_HOUR = 18;

export const minutesIntoDay = (date) => date.getHours() * 60 + date.getMinutes();

/** The hours to draw: 08:00-18:00, stretched to fit any block that starts earlier or ends later. */
export function visibleHours(blocks) {
  let start = DEFAULT_START_HOUR;
  let end = DEFAULT_END_HOUR;
  for (const block of blocks) {
    start = Math.min(start, Math.floor(minutesIntoDay(block.start) / 60));
    end = Math.max(end, Math.ceil(minutesIntoDay(block.end) / 60) || 24);
  }
  return { start, end };
}

/**
 * Give overlapping blocks side-by-side lanes. Blocks are grouped into clusters that overlap each
 * other; inside a cluster each block takes the first free lane, and every block in the cluster gets
 * width 1/lanes. Returns new objects with `lane` and `lanes` added.
 */
export function assignLanes(blocks) {
  const sorted = [...blocks].sort((a, b) => a.start - b.start || b.end - a.end);
  const placed = [];
  let cluster = [];
  let clusterEnd = -Infinity;
  let laneEnds = [];

  const closeCluster = () => {
    for (const block of cluster) block.lanes = laneEnds.length;
    cluster = [];
    laneEnds = [];
  };

  for (const original of sorted) {
    const block = { ...original };
    if (block.start >= clusterEnd) closeCluster();
    let lane = laneEnds.findIndex((end) => end <= block.start);
    if (lane === -1) lane = laneEnds.push(0) - 1;
    laneEnds[lane] = block.end;
    block.lane = lane;
    cluster.push(block);
    placed.push(block);
    clusterEnd = Math.max(clusterEnd, block.end);
  }
  closeCluster();
  return placed;
}
