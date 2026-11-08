import { Link } from "react-router-dom";
import { Page } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { EmptyState, Panel } from "@/components/ui/misc";

export default function NotFound() {
  return (
    <Page title="Page not found">
      <Panel><EmptyState title="There's nothing at this address" body="Check the link, or go back to the vendor list." action={<Link to="/"><Button>Back to vendors</Button></Link>} /></Panel>
    </Page>
  );
}
