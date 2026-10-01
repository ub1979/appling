import { Home } from "./pages/Home";
import { Settings } from "./pages/Settings";
import { Setup } from "./pages/Setup";
import { Studio } from "./pages/Studio";
import { PrefsProvider } from "./prefs";
import { useRoute } from "./router";

function Pages() {
  const route = useRoute();
  if (route.path.startsWith("/p/")) return <Studio key={route.path} id={route.path.slice(3)} />;
  if (route.path === "/settings") return <Settings key={route.params.get("project") ?? "all"} projectId={route.params.get("project")} />;
  if (route.path === "/new") return <Setup key="new" mode="new" styleId={route.params.get("style")} />;
  if (route.path === "/open") return <Setup key="open" mode="open" styleId={route.params.get("style")} />;
  return <Home />;
}

export function App() {
  return (
    <PrefsProvider>
      <Pages />
    </PrefsProvider>
  );
}
