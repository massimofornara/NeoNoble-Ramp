import "../core/env.js";
import { createApiServer } from "./server.js";

const port = Number(process.env.PORT || 4100);
const { server } = createApiServer();

server.listen(port, () => {
  console.log(JSON.stringify({ level: "info", component: "api-gateway", message: `listening on ${port}` }));
});
