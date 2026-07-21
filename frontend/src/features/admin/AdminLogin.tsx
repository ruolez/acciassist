import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { Logo } from "../../components/Logo";
import { api, ApiError } from "../../api/client";
import type { Admin } from "../../api/types";
import { usePageTitle } from "../../lib/usePageTitle";
import "./admin.css";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type LoginForm = z.infer<typeof schema>;

export function AdminLogin() {
  usePageTitle("Sign in");
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
      await api<Admin>("/admin/login", { method: "POST", body: values });
      await queryClient.invalidateQueries({ queryKey: ["admin", "me"] });
      navigate("/admin");
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Login failed");
    }
  };

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={handleSubmit(onSubmit)}>
        <Logo size={44} withWordmark />
        <h1>Admin sign in</h1>
        <p className="login-sub">The patient intake and case management panel.</p>
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
        <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
          Sign in
        </button>
      </form>
    </div>
  );
}
