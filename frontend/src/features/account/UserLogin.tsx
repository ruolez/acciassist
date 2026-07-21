import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { api, ApiError } from "../../api/client";
import type { User } from "../../api/types";
import { Logo } from "../../components/Logo";
import { usePageTitle } from "../../lib/usePageTitle";
import "./account.css";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type LoginForm = z.infer<typeof schema>;

export function UserLogin() {
  usePageTitle("Log in");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: LoginForm) => {
    setFormError(null);
    try {
      await api<User>("/auth/login", { method: "POST", body: values });
      await queryClient.invalidateQueries({ queryKey: ["user", "me"] });
      navigate("/account");
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Login failed");
    }
  };

  return (
    <div className="auth-page">
      <Logo size={44} withWordmark to="/" />
      <form className="card auth-card" onSubmit={handleSubmit(onSubmit)}>
        <h1>Log in to your case</h1>
        <p className="auth-sub">Follow your case progress and updates from our team.</p>
        {formError && <div className="error-text">{formError}</div>}
        <div className="field">
          <label>Email</label>
          <input className="input" type="email" {...register("email")} autoFocus />
          {errors.email && <span className="error-text">{errors.email.message}</span>}
        </div>
        <div className="field">
          <label>Password</label>
          <input className="input" type="password" {...register("password")} />
          {errors.password && <span className="error-text">{errors.password.message}</span>}
        </div>
        <button className="btn btn-cta" type="submit" disabled={isSubmitting}>
          Log in
        </button>
        <div className="auth-links">
          <Link to="/forgot-password">Forgot password?</Link>
          <Link to="/">Start a new case</Link>
        </div>
      </form>
    </div>
  );
}
