import { FormEvent, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { login } from "@/modules/auth/auth.api";
import { authSelectors, useAuthStore } from "@/modules/auth/auth.store";

export function AuthLoginPage() {
  const navigate = useNavigate();
  const setSessionFromAuthResponse = useAuthStore(authSelectors.setSessionFromAuthResponse);
  const [email, setEmail] = useState("admin@pgwarden.com");
  const [password, setPassword] = useState("admin");

  const loginMutation = useMutation({
    mutationFn: login,
  });

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const auth = await loginMutation.mutateAsync({ email, password });
    setSessionFromAuthResponse(auth);
    await navigate({ to: "/" });
  };

  return (
    <section className="sf-panel mx-auto mt-16 w-full max-w-md p-6">
      <p className="sf-label font-mono text-accent-amber">Secure Access</p>
      <h1 className="mt-1 font-display text-2xl tracking-wide text-foreground">Login</h1>

      <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
        <input
          className="app-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          required
        />
        <input
          className="app-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          required
        />

        {loginMutation.isError ? (
          <p className="text-xs text-rose-400">Login failed. Check credentials and API status.</p>
        ) : null}
        <button
          type="submit"
          className="app-button-primary w-full"
          disabled={loginMutation.isPending}
        >
          {loginMutation.isPending ? "Signing in..." : "Sign in"}
        </button>
      </form>

      <p className="mt-4 text-sm text-muted-foreground">
        No account yet?{" "}
        <Link className="app-link" to="/register">
          Create one
        </Link>
      </p>
    </section>
  );
}
