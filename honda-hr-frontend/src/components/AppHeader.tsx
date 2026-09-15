import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import Logo from "./Logo";
import { useAuth } from "../context/AuthContext";

/**
 * The one dark band on the page.
 *
 * Everything below it is cream and white so the working surfaces stay quiet;
 * the burgundy here is what carries the brand, and it does that once rather
 * than repeatedly.
 */

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `focus-ring relative rounded px-1 py-3 text-sm font-medium transition-colors ${
    isActive ? "text-white" : "text-wine-300 hover:text-white"
  }`;

const NavItem: React.FC<{ to: string; end?: boolean; children: React.ReactNode }> = ({
  to,
  end,
  children,
}) => (
  <NavLink to={to} end={end} className={navLinkClass}>
    {({ isActive }) => (
      <>
        {children}
        {/* The active marker is a rule under the word, not a filled pill —
            it reads as a tab without adding another shape to the bar.

            The bright red, not the base one. This bar is black, and the deep
            #8C1A1E on black is barely a shade apart from it — a 1.7:1 marker
            is not a marker. The logo beside it is printed in this same bright
            value anyway, so the header is internally consistent. */}
        <span
          aria-hidden
          className={`absolute inset-x-0 -bottom-px h-0.5 rounded-full transition-opacity ${
            isActive ? "bg-honda-red-bright opacity-100" : "opacity-0"
          }`}
        />
      </>
    )}
  </NavLink>
);

const AppHeader: React.FC = () => {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const leave = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  return (
    // A red rule along the bottom edge, so the black bar ends on the brand
    // rather than just stopping. It is also what separates the bar from the
    // page beneath it now that the page is barely tinted.
    <header
      className="sticky top-0 z-40 border-b-2 bg-wine-800"
      style={{ borderBottomColor: "#8C1A1E" }}
    >
      <div className="mx-auto flex h-[62px] max-w-shell items-center gap-6 px-5 lg:px-8">
        {/* The mark already says HONDA, so the name is not repeated beside it.
            What the bar needs to add is which system this is. */}
        <div className="flex shrink-0 items-center gap-3.5">
          <Logo tone="light" size={17} compact />
          <span aria-hidden className="h-5 w-px bg-white/20" />
          <span className="font-mono text-2xs font-medium uppercase tracking-[0.16em] text-wine-300">
            Recruitment
          </span>
        </div>

        <nav className="ml-2 hidden items-center gap-6 self-stretch md:flex">
          <NavItem to="/" end>
            Workspace
          </NavItem>
          <NavItem to="/history">History</NavItem>
          {user?.role === "admin" && <NavItem to="/admin">Administration</NavItem>}
          <NavItem to="/help">Help</NavItem>
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <p className="hidden font-mono text-2xs uppercase tracking-[0.14em] text-wine-300 xl:block">
            Decision support. A person decides
          </p>

          {user && (
            <div className="flex items-center gap-3 border-l border-white/10 pl-4">
              <div className="hidden text-right leading-tight sm:block">
                <div className="text-sm font-semibold text-white">{user.name}</div>
                <div className="font-mono text-2xs uppercase tracking-[0.12em] text-wine-300">
                  {user.role === "admin" ? "Administrator" : "HR"}
                </div>
              </div>
              <button
                onClick={leave}
                title="Sign out"
                aria-label="Sign out"
                className="focus-ring flex h-8 w-8 items-center justify-center rounded-md text-wine-300 transition-colors hover:bg-white/10 hover:text-white"
              >
                <LogOut size={15} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Small screens lose the inline nav; give it its own row rather than
          hiding pages behind a menu nobody finds. */}
      <nav className="flex items-center gap-5 border-t border-white/10 px-5 md:hidden">
        <NavItem to="/" end>
          Workspace
        </NavItem>
        <NavItem to="/history">History</NavItem>
        {user?.role === "admin" && <NavItem to="/admin">Admin</NavItem>}
        <NavItem to="/help">Help</NavItem>
      </nav>
    </header>
  );
};

export default AppHeader;
