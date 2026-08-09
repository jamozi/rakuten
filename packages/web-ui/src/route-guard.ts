import { createJsonValue } from './serializable.ts';

export const ADMIN_ROLES = [
  'PRODUCT_OWNER',
  'MANAGING_EDITOR',
  'EDITOR',
  'REVIEWER',
  'ANALYST',
  'OPERATOR',
  'SECURITY_AUDITOR',
  'READ_ONLY_AUDITOR',
] as const;

export type AdminRole = (typeof ADMIN_ROLES)[number];

export const ROUTE_DECISION_CODES = [
  'FEATURE_DISABLED',
  'UNREGISTERED_ROUTE',
  'UNAUTHENTICATED',
  'SITE_SCOPE_MISSING',
  'ROLE_SET_INVALID',
  'ROLE_DENIED',
  'ALLOW_UI_ONLY',
] as const;

export type RouteDecisionCode = (typeof ROUTE_DECISION_CODES)[number];

export type AdminRouteAvailability = 'DISABLED_AUTH_TRANSPORT_UNRESOLVED';

export interface AdminRouteRegistration {
  readonly screenId: 'ADM-001';
  readonly path: '/admin';
  readonly allowedRoles: readonly AdminRole[];
  readonly siteScopeRequired: true;
  readonly securityAuthority: 'server';
  readonly availability: AdminRouteAvailability;
}

const routeRegistrySource = [
  {
    screenId: 'ADM-001',
    path: '/admin',
    allowedRoles: ADMIN_ROLES,
    siteScopeRequired: true,
    securityAuthority: 'server',
    availability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
  },
] as const;

export const ADMIN_ROUTE_REGISTRY = createJsonValue(routeRegistrySource) as unknown as readonly [
  AdminRouteRegistration,
];

export interface AdminRouteRequest {
  readonly path: unknown;
  readonly authenticated: unknown;
  readonly siteScope: unknown;
  readonly roles: unknown;
}

export interface RouteDecision {
  readonly code: RouteDecisionCode;
  readonly routeId: 'ADM-001' | null;
  readonly availability: AdminRouteAvailability | null;
  readonly navigationEligible: boolean;
  readonly renderEligible: boolean;
  readonly authorizationGranted: false;
  readonly backendReauthorizationRequired: true;
  readonly securityAuthority: 'server';
  readonly statement: string;
}

const ROLE_SET = new Set<string>(ADMIN_ROLES);
const SITE_SCOPE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const STATEMENTS: Readonly<Record<RouteDecisionCode, string>> = Object.freeze({
  FEATURE_DISABLED:
    'Navigation and rendering are disabled until authentication transport is resolved.',
  UNREGISTERED_ROUTE: 'The route is not registered for navigation or rendering.',
  UNAUTHENTICATED: 'An authenticated UI context is required before navigation or rendering.',
  SITE_SCOPE_MISSING: 'A nonempty validated site scope is required before navigation or rendering.',
  ROLE_SET_INVALID: 'The supplied UI role set is invalid.',
  ROLE_DENIED: 'The supplied UI role set is not eligible for this route.',
  ALLOW_UI_ONLY:
    'Navigation and rendering are UI-only; the backend must reauthenticate and reauthorize every data access and effect.',
});

function routeFor(path: unknown): AdminRouteRegistration | null {
  if (path !== '/admin') {
    return null;
  }
  return ADMIN_ROUTE_REGISTRY[0];
}

function validatedRoles(value: unknown): readonly AdminRole[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const result: AdminRole[] = [];
  const seen = new Set<string>();
  for (const role of value) {
    if (typeof role !== 'string' || !ROLE_SET.has(role) || seen.has(role)) {
      return null;
    }
    seen.add(role);
    result.push(role as AdminRole);
  }
  return Object.freeze(result);
}

export function isValidSiteScope(value: unknown): value is string {
  return typeof value === 'string' && SITE_SCOPE.test(value);
}

function decision(code: RouteDecisionCode, route: AdminRouteRegistration | null): RouteDecision {
  const eligible = code === 'ALLOW_UI_ONLY';
  return createJsonValue({
    code,
    routeId: route?.screenId ?? null,
    availability: route?.availability ?? null,
    navigationEligible: eligible,
    renderEligible: eligible,
    authorizationGranted: false,
    backendReauthorizationRequired: true,
    securityAuthority: 'server',
    statement: STATEMENTS[code],
  }) as unknown as RouteDecision;
}

/**
 * Assesses UI context only. An ALLOW_UI_ONLY result never activates a route
 * and never represents server authorization.
 */
export function evaluateAdminRouteContext(request: AdminRouteRequest): RouteDecision {
  const route = routeFor(request.path);
  if (route === null) {
    return decision('UNREGISTERED_ROUTE', null);
  }
  if (request.authenticated !== true) {
    return decision('UNAUTHENTICATED', route);
  }
  if (!isValidSiteScope(request.siteScope)) {
    return decision('SITE_SCOPE_MISSING', route);
  }
  const roles = validatedRoles(request.roles);
  if (roles === null) {
    return decision('ROLE_SET_INVALID', route);
  }
  if (!roles.some((role) => route.allowedRoles.includes(role))) {
    return decision('ROLE_DENIED', route);
  }
  return decision('ALLOW_UI_ONLY', route);
}

/** Enforces the current disabled registration after context validation. */
export function evaluateAdminRoute(request: AdminRouteRequest): RouteDecision {
  const contextDecision = evaluateAdminRouteContext(request);
  if (contextDecision.code !== 'ALLOW_UI_ONLY') {
    return contextDecision;
  }
  return decision('FEATURE_DISABLED', ADMIN_ROUTE_REGISTRY[0]);
}
