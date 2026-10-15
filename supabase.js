import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm'

// Remplace par tes vraies valeurs récupérées sur Supabase
const supabaseUrl = 'https://dopgoecbdssvxexanavs.supabase.co/rest/v1/'
const supabaseKey = 'sb_publishable_5GrtRyqg1LV-wDZpFUxEnw_FHTDWbux'

export const supabase = createClient(supabaseUrl, supabaseKey)