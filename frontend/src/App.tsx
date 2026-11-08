import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { Spinner } from "@/components/ui/misc";

// Route-based code splitting: each screen is its own chunk.
const Login = lazy(() => import("@/routes/Login"));
const Dashboard = lazy(() => import("@/routes/Dashboard"));
const VendorDetail = lazy(() => import("@/routes/VendorDetail"));
const RunLive = lazy(() => import("@/routes/RunLive"));
const Runs = lazy(() => import("@/routes/Runs"));
const Outbox = lazy(() => import("@/routes/Outbox"));
const Demo = lazy(() => import("@/routes/Demo"));
const Portal = lazy(() => import("@/routes/Portal"));
const NotFound = lazy(() => import("@/routes/NotFound"));

function Loading() {
  return <div className="flex min-h-[50vh] items-center justify-center text-muted"><Spinner /><span className="sr-only">Loading</span></div>;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, checking } = useAuth();
  const location = useLocation();
  if (checking) return <Loading />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

const s = (el: ReactNode) => <Suspense fallback={<Loading />}>{el}</Suspense>;

const router = createBrowserRouter([
  { path: "/login", element: s(<Login />) },
  { path: "/portal/:token", element: s(<Portal />) },
  {
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { path: "/", element: s(<Dashboard />) },
      { path: "/vendors/:id", element: s(<VendorDetail />) },
      { path: "/runs", element: s(<Runs />) },
      { path: "/runs/:id", element: s(<RunLive />) },
      { path: "/outbox", element: s(<Outbox />) },
      { path: "/demo", element: s(<Demo />) },
      { path: "*", element: s(<NotFound />) },
    ],
  },
]);

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
