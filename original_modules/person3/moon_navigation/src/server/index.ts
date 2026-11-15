import { createApp } from "./app.js";
import { gridFromEnv } from "./terrain.js";

const port = Number(process.env.PORT ?? 3003);
const grid = gridFromEnv(); // LUNA_TERRAIN_GRID_JSON=<grid json> for real LOLA terrain, else MOCK fixture
createApp({ grid }).listen(port, () => {
  console.log(`moon_navigation API listening on http://localhost:${port}/api/v1 (terrain: ${grid.source.name}, ${grid.source.data_status})`);
});
