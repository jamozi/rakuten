import { createPublicPolicyMetadata } from '../../src/public-policy';
import { PublicPolicyPage } from '../../src/public-shell';

export const dynamic = 'force-dynamic';
export const metadata = createPublicPolicyMetadata('PUB-004');

export default function EditorialPolicyPage() {
  return <PublicPolicyPage screenId="PUB-004" />;
}
