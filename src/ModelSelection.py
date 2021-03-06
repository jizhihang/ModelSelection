from numpy import linalg
from RandomVariables import *
from Hypotheses import HypothesisCollection

class LinearRegression:
    """ Use Occam's razor to select among one of several possible hypotheses.

    Each hypothesis models target values using

            \[ t = y (x, w) + \epsilon, \]

    where

            \[ y (x, w) = \sum_{j = 0}^{M-1} w_j \phi_j (x) \]

    is some choice of basis functions $\phi_j$, and $\epsilon$ is Gaussian noise.
    """
    def __init__(self, collectionOfHypotheses, observationNoise):
        assert isinstance(collectionOfHypotheses, HypothesisCollection)
        assert np.isreal(observationNoise)

        self.hypotheses = collectionOfHypotheses   # list of hypotheses
        self.numHyp = len(collectionOfHypotheses)  # number of hypotheses
        self.XHist = np.array([])                  # list of all past x values: dynamic
        self.THist = np.array([])                  # list of all past t values: dynamic
        self.sigma = observationNoise              # Gaussian noise on the target values
        self.parameter = []                        # k-th entry: p(w|data, H_k)

        # history of past fitting parameters m and S
        self.mHist = [[] for i in range(self.numHyp)]
        self.SHist = [[] for i in range(self.numHyp)]
        self.probHyp = [[] for i in range(self.numHyp)]

        # History of past Phi matrices, one per each hypothesis
        self.Phis = [np.ndarray((0,self.hypotheses[i].M)) for i in range(self.numHyp)]

        for k, hyp in enumerate(self.hypotheses):
            assert isinstance(hyp.parameterPrior, DiagonalGaussianRV)
            # set p(H_k|"nodata") = p(H_k)
            self.probHyp[k].append(self.hypotheses.prior.evaluate(k))

            # set $p(w|"no data", H_k) = p(w|H_k)$ for all k:
            # (i.e. set the prior of the regression to the natural prior of the hypothesis)
            self.parameter.append(GaussianRV(hyp.parameterPrior.mean, hyp.parameterPrior.variance))

    def update(self, newX, newT):
        """ Bayesian linear regression update.

        For every hypothesis k this method computes the posterior probability
            p(w|THist, newT, H_k)

        This depends strongly on all Gaussian assumptions!

        :param newX: New value of the input variable (transposed)
        :param newT: New value of the target variable (transposed)
        :return:
        """

        #############################################################
        # first: parameter estimation for each hypothesis
        #############################################################

        self.XHist = np.append(self.XHist, newX)
        self.THist = np.append(self.THist, newT)

        for k, (hyp, currentPara) in enumerate(zip(self.hypotheses, self.parameter)):
            # get Phi (depends on newX) from hypothesis k
            Phi = hyp.evaluate(newX)

            # new covariance matrix
            SNInv = currentPara.inv_variance + np.dot(np.transpose(Phi), Phi) / self.sigma ** 2
            temp = np.dot(currentPara.inv_variance, currentPara.mean) + \
                   np.transpose(Phi) * newT / self.sigma ** 2
            currentPara.inv_variance = SNInv  # update inverse variance and variance
            # SN = linalg.inv(SNInv) is not needed, as setter of GaussianDistribution calculates it
            mN = np.dot(currentPara.variance, temp)

            # update all other variables
            currentPara.mean = mN
            self.mHist[k].append(mN)
            self.SHist[k].append(currentPara.variance)

        #############################################################
        # second: model selection
        #############################################################

        unnormalizedEvidence = np.zeros((self.numHyp, 1))
        for k, (hyp, currentPara) in enumerate(zip(self.hypotheses, self.parameter)):
            # get sigma_W from hypothesis: SIGMA = sigmaWSQ * Id_M
            sigmaWSQ = hyp.parameterPrior.factor
            # Update Phi matrix from all past data with current data
            self.Phis[k] = np.vstack((self.Phis[k], hyp.evaluate(newX)))
            Phi = self.Phis[k]      # alias
            N   = Phi.shape[0]      # number of data points
            M   = Phi.shape[1]      # number of parameters w

            # model selection:

            A = (np.dot(np.transpose(Phi), Phi) / self.sigma ** 2 + np.eye(M, M) / sigmaWSQ)

            # numerator 1 of model selection formula

            # w^T*Phi (the y-Value according to the fitted model)
            modelMeanOfT = np.dot(Phi, currentPara.mean)
            randomVariable = DiagonalGaussianRV(modelMeanOfT, self.sigma ** 2)
            temp = self.THist.reshape(N, -1)
            # the probability of t given y (when there is noise)
            num1 = randomVariable.evaluate(temp)

            # numerator 2 of model selection formula:
            # just the prior probability of the MAP-estimation
            num2 = hyp.parameterPrior.evaluate(currentPara.mean)

            # denominator of model selection formula:
            denom = math.sqrt(linalg.det(A / (2 * np.pi)))

            # unnormalized Evidence
            unnormalizedEvidence[k] = num1 * num2 / denom

        # normalize and save

        normalization = np.sum(unnormalizedEvidence)
        for k, prob in enumerate(self.probHyp):
            normed = unnormalizedEvidence[k] / normalization
            prob.append(normed)

    def update_old(self, newX, newT):   #newX=x',newT=t'
        """ Original implementation
        :param newX:
        :param newT:
        :return:
        """
        # ------------------------------------------------
        # first: parameter estimation for each hypothesis
        # ------------------------------------------------

        self.XHist = np.append(self.XHist, newX)
        self.THist = np.append(self.THist, newT)


        for k in range(self.numHyp): # for every hypothesis


            # get priors
            m = self.parameter[k].mean
            SInv = self.parameter[k].inv_variance

            # get Phi (depends on newX) from hypothesis k
            Phi = self.hypotheses[k].evaluate([newX])

            # new covariance matrix
            SNInv = SInv + np.dot(np.transpose(Phi), Phi)/self.sigma**2

            # SN = linalg.inverse(SNInv) is not needed, as setter
            # of class GaussianDistribution calculates it automatically

            temp = np.dot(SInv, m) + np.transpose(Phi)*newT/self.sigma**2
            SN = linalg.inv(SNInv)
            mN = np.dot(SN, temp)

            # update all variables
            self.parameter[k].mean = mN
            self.parameter[k].inv_variance = SNInv
            # variance gets calculated inside class automatically
            self.mHist[k].append(mN)
            self.SHist[k].append(self.parameter[k].variance)



        # --------------------------------------------------
        # second: model selection
        # --------------------------------------------------

        # initialize all needed containers
        PhiL = []
        mL = []
        SL = []

        unnormalizedEvidence = np.zeros((self.numHyp, 1))
        for k in range(self.numHyp):
            # get sigma_W from hypothesis: SIGMA = sigmaWSQ * Id_M
            sigmaWSQ = self.hypotheses[k].parameterPrior.factor
            # build huge Phi matrix from all past data and insert in index k
            # so PhiL is a list of Phi matrices
            PhiL.append(self.hypotheses[k].evaluate(self.XHist))
            Phi = PhiL[k] # matrix Phi for the current hypothesis
            N = Phi.shape[0] # number of data points
            M = Phi.shape[1] # number of parameters w

            # model selection:

            A = (np.dot(np.transpose(Phi), Phi)/self.sigma**2 +
                np.eye(M, M)/sigmaWSQ)

            currentPara = self.parameter[k]

            # numerator 1 of model selection formula

            # w^T*Phi (the y-Value according to the fitted model)
            modelMeanOfT = np.dot(Phi, currentPara.mean)
            randomVariable = GaussianRV(modelMeanOfT,
                                        self.sigma**2*np.eye(N, N))
            temp = self.THist.reshape(N, -1)
            # the probability of t given y (when there is noise)
            num1 = randomVariable.evaluate(temp)

            currentHypo = self.hypotheses[k]

            # numerator 2 of model selection formula:
            # just the prior probability of the MAP-estimation
            num2 = currentHypo.parameterPrior.evaluate(currentPara.mean)

            # denominator of model selection formula:
            denom = math.sqrt(linalg.det(A/(2*np.pi)))

            # unnormalized Evidence
            unnormalizedEvidence[k] = num1*num2/denom

        normalization = np.sum(unnormalizedEvidence)
        for k in range(self.numHyp):  # normalize and save
            normed = unnormalizedEvidence[k]/normalization
            #print(normed)
            self.probHyp[k].append(normed)