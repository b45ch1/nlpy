"""
Solve the least-squares problem

  minimize ||Ax-b||

using LSQR.  This is a line-by-line translation from Matlab code
available at http://www.stanford.edu/~saunders/lsqr.

Michael P. Friedlander, University of British Columbia
Dominique Orban, Ecole Polytechnique de Montreal
"""

from nlpy.tools.utils import roots_quadratic
from numpy import zeros, dot, inf
from numpy.linalg import norm
from math import sqrt

__docformat__ = 'restructuredtext'

# Simple shortcuts---linalg.norm is too slow for small vectors
def normof2(x,y): return sqrt(x**2 + y**2)
def normof4(x1,x2,x3,x4): return sqrt(x1**2 + x2**2 + x3**2 + x4**2)

class LSQRFramework:
    r"""
    LSQR solves  `Ax = b`  or  `minimize |b - Ax|` in Euclidian norm  if
    `damp = 0`, or `minimize |b - Ax| + damp * |x|` in Euclidian norm if
    `damp > 0`.

    `A`  is an (m x n) linear operator defined by  `y = A * x` (or `y = A(x)`),
    where `y` is the result of applying the linear operator to `x`. Application
    of transpose linear operator must be accessible via `u = A.T * x` (or
    `u = A.T(x)`). The shape of the linear operator `A` must be accessible via
    `A.shape`. A convenient way to achieve this is to make sure that `A` is
    a `LinearOperator` instance.

    LSQR uses an iterative (conjugate-gradient-like) method.

    For further information, see

    1. C. C. Paige and M. A. Saunders (1982a).
       LSQR: An algorithm for sparse linear equations and sparse least
       squares, ACM TOMS 8(1), 43-71.
    2. C. C. Paige and M. A. Saunders (1982b).
       Algorithm 583. LSQR: Sparse linear equations and least squares
       problems, ACM TOMS 8(2), 195-209.
    3. M. A. Saunders (1995).  Solution of sparse rectangular systems using
       LSQR and CRAIG, BIT 35, 588-604.
    """

    def __init__(self, A):

        # Initialize.

        self.msg=['The exact solution is  x = 0                              ',
                  'Ax - b is small enough, given atol, btol                  ',
                  'The least-squares solution is good enough, given atol     ',
                  'The estimate of cond(Abar) has exceeded conlim            ',
                  'Ax - b is small enough for this machine                   ',
                  'The least-squares solution is good enough for this machine',
                  'Cond(Abar) seems to be too large for this machine         ',
                  'The iteration limit has been reached                      ',
                  'The trust-region boundary has been hit                    ']

        self.A = A
        self.x = None ; self.var = None

        self.itn = 0; self.istop = 0; self.nstop = 0
        self.anorm = 0.; self.acond = 0. ; self.arnorm = 0.
        self.xnorm = 0.;
        self.r1norm = 0.; self.r2norm = 0.
        return

    def solve(self, rhs, itnlim=0, damp=0.0,
              atol=1.0e-9, btol=1.0e-9, conlim=1.0e+8, radius=None,
              show=False, wantvar=False):
        """
        Solve the linear system, linear least-squares problem or regularized
        linear least-squares problem with specified parameters. All return
        values below are stored in members of the same name.

        :parameters:

           :rhs:    right-hand side vector.
           :itnlim: is an explicit limit on iterations (for safety).
           :damp:   damping/regularization parameter.

        :keywords:

           :atol:
           :btol:  are stopping tolerances.  If both are 1.0e-9 (say),
                   the final residual norm should be accurate to about 9 digits.
                   (The final x will usually have fewer correct digits,
                   depending on `cond(A)` and the size of `damp`.)
           :conlim: is also a stopping tolerance.  lsqr terminates if an
                    estimate of `cond(A)` exceeds `conlim`.  For compatible
                    systems `Ax = b`, `conlim` could be as large as 1.0e+12
                    (say).  For least-squares problems, `conlim` should be less
                    than 1.0e+8. Maximum precision can be obtained by setting
                    `atol` = `btol` = `conlim` = zero, but the number of
                    iterations may then be excessive.
           :radius: an optional trust-region radius (default: None).
           :show:   if set to `True`, gives an iteration log.
                    If set to `False`, suppresses output.

        :return:

           :x:     is the final solution.
           :istop: gives the reason for termination.
           :istop: = 1 means x is an approximate solution to Ax = b.
                   = 2 means x approximately solves the least-squares problem.
           :r1norm: = norm(r), where r = b - Ax.
           :r2norm: = sqrt(norm(r)^2  +  damp^2 * norm(x)^2)
                    = r1norm if damp = 0.
           :anorm: = estimate of Frobenius norm of (regularized) A.
           :acond: = estimate of cond(Abar).
           :arnorm: = estimate of norm(A'r - damp^2 x).
           :xnorm: = norm(x).
           :var:   (if present) estimates all diagonals of (A'A)^{-1}
                   (if damp=0) or more generally (A'A + damp^2*I)^{-1}.
                   This is well defined if A has full column rank or damp > 0.
                   (Not sure what var means if rank(A) < n and damp = 0.)
        """

        A = self.A
        m, n = A.shape

        if itnlim == 0: itnlim = 3*n

        if wantvar:
            var = zeros(n,1)
        else:
            var = None
        dampsq = damp**2;

        itn = 0 ; istop = 0 ; nstop = 0
        ctol = 0.0
        if conlim > 0.0: self.ctol = 1.0/conlim
        anorm = 0. ; acond = 0.
        cs2 = -1. ; sn2 = 0.
        z = 0.
        xnorm = 0. ; xxnorm = 0. ; ddnorm = 0. ; res2 = 0.

        tr_active = False
        if radius is None:
            stepMax = None

        if show:
            print ' '
            print 'LSQR            Least-squares solution of  Ax = b'
            str1='The matrix A has %8d rows and %8d cols' % (m, n)
            str2='damp = %20.14e     wantvar = %-5s' % (damp, repr(wantvar))
            str3='atol = %8.2e                 conlim = %8.2e' % (atol,conlim)
            str4='btol = %8.2e                 itnlim = %8g' % (btol, itnlim)
            print str1; print str2; print str3; print str4;

        # Set up the first vectors u and v for the bidiagonalization.
        # These satisfy  beta*u = b,  alfa*v = A'u.

        x = zeros(n)
        u = rhs[:m].copy()
        alfa = 0. ; beta = norm(u)
        if beta > 0:
            u /= beta; v = A.T * u
            alfa = norm(v)

        if alfa > 0:
            v /= alfa; w = v.copy()

        x_is_zero = False   # Is x=0 the solution to the least-squares prob?
        arnorm = alfa * beta
        if arnorm == 0.0:
            print self.msg[0]
            x_is_zero = True
            istop = 0
            #return

        rhobar = alfa ; phibar = beta ; bnorm  = beta
        rnorm  = beta
        r1norm = rnorm
        r2norm = rnorm
        head1  = '   Itn      x(1)       r1norm     r2norm '
        head2  = ' Compatible   LS      Norm A   Cond A'

        if show:
            print ' '
            print head1+head2
            test1  = 1.0;		test2  = alfa / beta
            str1   = '%6g %12.5e'     % (itn,    x[0])
            str2   = ' %10.3e %10.3e' % (r1norm, r2norm)
            str3   = '  %8.1e %8.1e'  % (test1,  test2)
            print str1+str2+str3

        # ------------------------------------------------------------------
        #     Main iteration loop.
        # ------------------------------------------------------------------
        while itn < itnlim and not x_is_zero:
            itn = itn + 1
            #   Perform the next step of the bidiagonalization to obtain the
            #   next  beta, u, alfa, v.  These satisfy the relations
            #              beta*u  =  a*v   -  alfa*u,
            #              alfa*v  =  A'*u  -  beta*v.

            u    = A * v  -  alfa * u
            beta = norm(u)
            if beta > 0:
                u    /= beta
                anorm = normof4(anorm, alfa, beta, damp)
                v     = A.T * u - beta * v
                alfa  = norm(v)
                if alfa > 0:  v /= alfa

            # Use a plane rotation to eliminate the damping parameter.
            # This alters the diagonal (rhobar) of the lower-bidiagonal matrix.

            rhobar1 = normof2(rhobar, damp)
            cs1     = rhobar / rhobar1
            sn1     = damp   / rhobar1
            psi     = sn1 * phibar
            phibar  = cs1 * phibar

            #  Use a plane rotation to eliminate the subdiagonal element (beta)
            # of the lower-bidiagonal matrix, giving an upper-bidiagonal matrix.

            rho     =   normof2(rhobar1, beta)
            cs      =   rhobar1/ rho
            sn      =   beta   / rho
            theta   =   sn * alfa
            rhobar  = - cs * alfa
            phi     =   cs * phibar
            phibar  =   sn * phibar
            tau     =   sn * phi

            # Update x and w.

            t1      =   phi  /rho;
            t2      = - theta/rho;
            dk      =   (1.0/rho)*w;

            if radius is not None:
                # Calculate distance to trust-region boundary from x along w.
                xw = dot(x,w)
                ww = dot(w,w)  # Can be updated at each iter ?

                # Obtain roots of quadratic to determine intersection of
                # the search direction with the trust-region boundary.
                roots = roots_quadratic(ww, 2*xw, xnorm*xnorm - radius*radius)

                # Select largest real root in absolute value with the same
                # sign as t1.
                stepMax = max([abs(r) for r in roots if r*t1 > 0])

                if abs(t1) > abs(stepMax):
                    x += stepMax * w
                    xnorm = radius
                    r1norm = normof2(rho*stepMax*sn, rho*stepMax*cs - phibar)
                    tr_active = True
                    istop = 8

            if not tr_active:
                x      += t1*w
                w      *= t2 ; w += v
                ddnorm  = ddnorm + norm(dk)**2
                if wantvar: var += dk*dk

                # Use a plane rotation on the right to eliminate the
                # super-diagonal element (theta) of the upper-bidiagonal matrix.
                # Then use the result to estimate norm(x).

                delta   =   sn2 * rho
                gambar  = - cs2 * rho
                rhs     =   phi  -  delta * z
                zbar    =   rhs / gambar
                xnorm   =   sqrt(xxnorm + zbar**2)
                gamma   =   normof2(gambar, theta)
                cs2     =   gambar / gamma
                sn2     =   theta  / gamma
                z       =   rhs    / gamma
                xxnorm +=   z*z

                # Test for convergence.
                # First, estimate the condition of the matrix  Abar,
                # and the norms of  rbar  and  Abar'rbar.

                acond   =   anorm * sqrt(ddnorm)
                res1    =   phibar**2
                res2    =   res2  +  psi**2
                rnorm   =   sqrt(res1 + res2)
                arnorm  =   alfa * abs(tau)

                # 07 Aug 2002:
                # Distinguish between
                #    r1norm = ||b - Ax|| and
                #    r2norm = rnorm in current code
                #           = sqrt(r1norm^2 + damp^2*||x||^2).
                #    Estimate r1norm from
                #    r1norm = sqrt(r2norm^2 - damp^2*||x||^2).
                # Although there is cancellation, it might be accurate enough.

                r1sq    =   rnorm**2  -  dampsq * xxnorm
                r1norm  =   sqrt(abs(r1sq))
                if r1sq < 0: r1norm = - r1norm
                r2norm  =   rnorm

                # Now use these norms to estimate certain other quantities,
                # some of which will be small near a solution.

                test1 = rnorm / bnorm
                test2 = arnorm/(anorm * rnorm)
                if acond == 0.0:
                    test3 = inf
                else:
                    test3 = 1.0 / acond
                t1    = test1 / (1    +  anorm * xnorm / bnorm)
                rtol  = btol  +  atol *  anorm * xnorm / bnorm

                # The following tests guard against extremely small values of
                # atol, btol  or  ctol.  (The user may have set any or all of
                # the parameters  atol, btol, conlim  to 0.)
                # The effect is equivalent to the normal tests using
                # atol = eps,  btol = eps,  conlim = 1/eps.

                if itn >= itnlim:  istop = 7
                if 1 + test3 <= 1: istop = 6
                if 1 + test2 <= 1: istop = 5
                if 1 + t1    <= 1: istop = 4

                # Allow for tolerances set by the user.

                if test3 <= ctol: istop = 3
                if test2 <= atol: istop = 2
                if test1 <= rtol: istop = 1

                # See if it is time to print something.

                prnt = False;
                if n     <= 40       : prnt = True
                if itn   <= 10       : prnt = True
                if itn   >= itnlim-10: prnt = True
                if itn % 10 == 0     : prnt = True
                if test3 <=  2*ctol  : prnt = True
                if test2 <= 10*atol  : prnt = True
                if test1 <= 10*rtol  : prnt = True
                if istop !=  0       : prnt = True

                if prnt and show:
                    str1 = '%6g %12.5e'     % (  itn,   x[0])
                    str2 = ' %10.3e %10.3e' % (r1norm, r2norm)
                    str3 = '  %8.1e %8.1e'  % (test1,  test2)
                    str4 = ' %8.1e %8.1e'   % (anorm,  acond)
                    print str1+str2+str3+str4

            if istop > 0: break

            # End of iteration loop.
            # Print the stopping condition.

        if show:
            print ' '
            print 'LSQR finished'
            print self.msg[istop]
            print ' '
            str1 = 'istop =%8g   r1norm =%8.1e'   % (istop, r1norm)
            str2 = 'anorm =%8.1e   arnorm =%8.1e' % (anorm, arnorm)
            str3 = 'itn   =%8g   r2norm =%8.1e'   % ( itn, r2norm)
            str4 = 'acond =%8.1e   xnorm  =%8.1e' % (acond, xnorm )
            str5 = '                  bnorm  =%8.1e'    % bnorm
            print str1 + '   ' + str2
            print str3 + '   ' + str4
            print str5
            print ' '

        if istop == 0: self.status = 'solution is zero'
        if istop in [1,2,4,5]: self.status = 'residual small'
        if istop in [3,6]: self.status = 'ill-conditioned operator'
        if istop == 7: self.status = 'max iterations'
        if istop == 8: self.status = 'trust-region boundary active'
        self.onBoundary = tr_active
        self.x = x
        self.istop = istop
        self.itn = itn
        self.r1norm = r1norm
        self.r2norm = r2norm
        self.anorm = anorm
        self.acond = acond
        self.arnorm = arnorm
        self.xnorm = xnorm
        self.var = var
        return
