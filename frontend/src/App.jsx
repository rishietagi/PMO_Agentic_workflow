import * as React from "react";
import { Sidebar } from "@/components/Sidebar";
import { RunView } from "@/components/RunView";
import { Dashboard } from "@/components/Dashboard";
import { getStatus } from "@/lib/api";

export default function App() {
  const [view, setView] = React.useState("run");
  const [status, setStatus] = React.useState(null);
  const [dashKey, setDashKey] = React.useState(0);

  React.useEffect(() => { getStatus().then(setStatus).catch(() => setStatus({})); }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar view={view} setView={setView} status={status} />
      <main className="h-screen flex-1 overflow-y-auto px-8 py-8 lg:px-12">
        <div className="mx-auto max-w-6xl">
          {view === "run" ? (
            <RunView status={status} onFeedback={() => setDashKey((k) => k + 1)} />
          ) : (
            <Dashboard refreshKey={dashKey} />
          )}
        </div>
      </main>
    </div>
  );
}
