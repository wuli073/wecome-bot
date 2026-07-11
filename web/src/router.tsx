import React, { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';

// Layouts
import RegisterLayout from '@/app/register/layout';
import ResetPasswordLayout from '@/app/reset-password/layout';
import HomeLayout from '@/app/home/layout';

// Pages
import ErrorPage from '@/components/ErrorPage';
import BackendUnavailablePage from '@/components/BackendUnavailablePage';
import RootLayout from '@/app/RootLayout';

const RegisterPage = React.lazy(() => import('@/app/register/page'));
const ResetPasswordPage = React.lazy(() => import('@/app/reset-password/page'));
const WizardPage = React.lazy(() => import('@/app/wizard/page'));
const SpaceCallbackPage = React.lazy(() => import('@/app/auth/space/callback/page'));
const MonitoringPage = React.lazy(() => import('@/app/home/monitoring/page'));
const BotsPage = React.lazy(() => import('@/app/home/bots/page'));
const PipelinesPage = React.lazy(() => import('@/app/home/pipelines/page'));
const PluginsPage = React.lazy(() => import('@/app/home/plugins/page'));
const AddExtensionPage = React.lazy(() => import('@/app/home/add-extension/page'));
const MCPPage = React.lazy(() => import('@/app/home/mcp/page'));
const KnowledgePage = React.lazy(() => import('@/app/home/knowledge/page'));
const SkillsPage = React.lazy(() => import('@/app/home/skills/page'));
const BroadcastPage = React.lazy(() => import('@/app/home/broadcast/page'));
const DatabaseModeRedirect = React.lazy(() => import('@/app/home/database-mode/redirect'));
const PluginPagesPage = React.lazy(() => import('@/app/home/plugin-pages/page'));

const Loading = () => <div>Loading...</div>;

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      {
        path: '/',
        element: <Navigate to="/home/monitoring" replace />,
      },
      {
        path: '/login',
        element: <Navigate to="/home/monitoring" replace />,
      },
      {
        path: '/register',
        element: (
          <RegisterLayout>
            <RegisterPage />
          </RegisterLayout>
        ),
      },
      {
        path: '/reset-password',
        element: (
          <ResetPasswordLayout>
            <ResetPasswordPage />
          </ResetPasswordLayout>
        ),
      },
      {
        path: '/wizard',
        element: <WizardPage />,
      },
      {
        path: '/backend-unavailable',
        element: <BackendUnavailablePage />,
      },
      {
        path: '/auth/space/callback',
        element: <SpaceCallbackPage />,
      },
      {
        path: '/home',
        element: <Navigate to="/home/monitoring" replace />,
      },
      {
        path: '/home/monitoring',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <MonitoringPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/bots',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <BotsPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/pipelines',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <PipelinesPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/extensions',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <PluginsPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/add-extension',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <AddExtensionPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/mcp',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <MCPPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/knowledge',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <KnowledgePage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/broadcast',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <BroadcastPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/database-mode',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <DatabaseModeRedirect />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/skills',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <SkillsPage />
            </HomeLayout>
          </Suspense>
        ),
      },
      {
        path: '/home/plugin-pages',
        element: (
          <Suspense fallback={<Loading />}>
            <HomeLayout>
              <PluginPagesPage />
            </HomeLayout>
          </Suspense>
        ),
      },
    ],
  },
]);
