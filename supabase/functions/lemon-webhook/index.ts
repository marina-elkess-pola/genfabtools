import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
);

serve(async (req: Request): Promise<Response> => {
    try {
        if (req.method !== "POST") {
            return new Response("ok", { status: 200 });
        }

        const raw = await req.text();
        const payload = JSON.parse(raw);

        const event = payload?.meta?.event_name;
        const email = payload?.data?.attributes?.user_email;

        console.log("EVENT:", event);
        console.log("EMAIL:", email);

        if (event === "subscription_payment_success" && email) {
            await supabase.from("subscriptions").upsert({
                email,
                status: "active",
                product: "RSI",
                created_at: new Date().toISOString()
            });
        }

        return new Response("ok", { status: 200 });
    } catch (err) {
        console.error(err);
        return new Response("ok", { status: 200 });
    }
});
