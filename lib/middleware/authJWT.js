import { verifyToken } from '../utils/jwt';

/**
 * Middleware to authenticate JWT tokens from Authorization header or cookie
 * Attaches user object to request if valid
 */
export async function authJWT(request) {
  // Try to get token from Authorization header
  const authHeader = request.headers.get('authorization');
  let token = authHeader?.replace('Bearer ', '');

  // If no Authorization header, try cookie
  if (!token) {
    const cookies = request.headers.get('cookie');
    if (cookies) {
      const tokenMatch = cookies.match(/token=([^;]+)/);
      token = tokenMatch?.[1];
    }
  }

  if (!token) {
    return {
      authenticated: false,
      error: 'No token provided',
    };
  }

  const decoded = verifyToken(token);
  if (!decoded) {
    return {
      authenticated: false,
      error: 'Invalid or expired token',
    };
  }

  return {
    authenticated: true,
    user: decoded,
  };
}

/**
 * Require authentication for a route handler
 */
export async function requireAuth(request) {
  const auth = await authJWT(request);
  
  if (!auth.authenticated) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'UNAUTHORIZED',
        message: auth.error || 'Authentication required',
      },
    };
  }

  return {
    ok: true,
    user: auth.user,
  };
}

/**
 * Require admin role
 */
export async function requireAdmin(request) {
  const auth = await requireAuth(request);
  
  if (!auth.ok) {
    return auth;
  }

  if (auth.user.role !== 'ADMIN') {
    return {
      ok: false,
      status: 403,
      body: {
        error: 'FORBIDDEN',
        message: 'Admin access required',
      },
    };
  }

  return {
    ok: true,
    user: auth.user,
  };
}