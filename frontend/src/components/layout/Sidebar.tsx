import {
  Bell,
  Bot,
  FileText,
  Globe,
  LayoutDashboard,
  LogOut,
  Search,
  Settings,
  Target,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import { getUnreadCount, onAlertsChanged } from '@/services/alerts';
import { useAuth } from '@/store/AuthContext';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

// Ordered to follow the workflow: configure Sources -> review Opportunities they
// produce -> Search across them -> analyze with the Copilot -> Reports -> Alerts.
const navigation = [
  { label: 'Dashboard', href: '/', icon: LayoutDashboard },
  { label: 'Sources', href: '/sources', icon: Globe },
  { label: 'Opportunities', href: '/opportunities', icon: Target },
  { label: 'Search', href: '/search', icon: Search },
  { label: 'AI Copilot', href: '/copilot', icon: Bot },
  { label: 'Reports', href: '/reports', icon: FileText },
  { label: 'Alerts', href: '/alerts', icon: Bell },
  { label: 'Admin', href: '/admin', icon: Settings, adminOnly: true },
];

const Sidebar = ({ isOpen, onClose }: SidebarProps) => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [unreadAlerts, setUnreadAlerts] = useState(0);

  const refreshUnread = useCallback(() => {
    getUnreadCount()
      .then((result) => setUnreadAlerts(result?.count ?? 0))
      .catch(() => {
        // badge is optional; ignore failures
      });
  }, []);

  // Refresh the unread badge on mount, on route change, and whenever alerts are marked
  // read elsewhere (e.g. on /alerts, where the route doesn't change).
  useEffect(() => {
    refreshUnread();
  }, [pathname, refreshUnread]);

  useEffect(() => onAlertsChanged(refreshUnread), [refreshUnread]);

  const filteredNavigation = navigation.filter((item) => !item.adminOnly || user?.role === 'admin');
  const initials = user?.full_name
    ?.split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActiveRoute = (href: string) => {
    if (href === '/') {
      return pathname === '/';
    }

    return pathname.startsWith(href);
  };

  return (
    <>
      <div
        className={[
          'fixed inset-0 z-30 bg-slate-950/40 transition-opacity lg:hidden',
          isOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        ].join(' ')}
        onClick={onClose}
      />

      <aside
        className={[
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white shadow-xl transition-transform lg:translate-x-0 lg:shadow-none',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        ].join(' ')}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">AI-Powered</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">RFP Intelligence</h1>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-5">
          {filteredNavigation.map(({ label, href, icon: Icon }) => {
            const active = isActiveRoute(href);

            return (
              <NavLink
                key={href}
                to={href}
                onClick={onClose}
                className={[
                  'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                  active
                    ? 'bg-blue-50 text-blue-700 shadow-sm ring-1 ring-blue-100'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                ].join(' ')}
              >
                <Icon className={['h-5 w-5', active ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-700'].join(' ')} />
                <span>{label}</span>
                {label === 'Alerts' && unreadAlerts > 0 ? (
                  <span className="ml-auto inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white">
                    {unreadAlerts > 99 ? '99+' : unreadAlerts}
                  </span>
                ) : null}
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-slate-200 p-4">
          <div className="mb-3 flex items-center gap-3 rounded-2xl bg-slate-50 p-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
              {initials || 'RI'}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{user?.full_name ?? 'Guest User'}</p>
              <p className="truncate text-xs text-slate-500">{user?.email ?? 'Not signed in'}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-100"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
