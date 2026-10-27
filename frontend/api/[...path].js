import { proxy } from "../server/proxy.js";

export default function handler(request, response) {
  return proxy(request, response, "/api");
}
