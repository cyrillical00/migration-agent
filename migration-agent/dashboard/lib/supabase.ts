import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Supabase client is used only for realtime subscriptions.
// All data mutations and reads go through the agent API.
export const supabase = createClient(supabaseUrl, supabaseAnonKey);
