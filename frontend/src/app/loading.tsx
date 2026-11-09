import { Skeleton } from "@/components/ui/feedback";

export default function RootLoading() {
  return (
    <div className="ds-app-shell" aria-label="Loading application">
      <aside className="ds-sidebar" aria-hidden="true">
        <div className="ds-sidebar-head"><Skeleton shape="control" /></div>
        <div className="ds-nav"><Skeleton shape="row" /><Skeleton shape="row" /></div>
      </aside>
      <header className="ds-topbar" aria-hidden="true"><Skeleton shape="text" /></header>
      <main className="ds-route-main"><Skeleton shape="panel" /></main>
    </div>
  );
}
