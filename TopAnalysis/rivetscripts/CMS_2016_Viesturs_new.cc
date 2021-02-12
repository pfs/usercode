#include "Rivet/Analysis.hh"
#include "Rivet/Projections/FinalState.hh"
#include "Rivet/Projections/FastJets.hh"
#include "Rivet/Projections/ChargedLeptons.hh"
#include "Rivet/Projections/DressedLeptons.hh"
#include "Rivet/Projections/IdentifiedFinalState.hh"
#include "Rivet/Projections/PromptFinalState.hh"
#include "Rivet/Projections/VetoedFinalState.hh"
#include "Rivet/Projections/InvMassFinalState.hh"
#include "Rivet/Projections/MissingMomentum.hh"
#include "Rivet/Math/MatrixN.hh"

#include "fastjet/contrib/Nsubjettiness.hh"
#include "fastjet/contrib/EnergyCorrelator.hh"
namespace Rivet 
{
  class CMS_2016_Viesturs_new: public Analysis{
  public:
    DEFAULT_RIVET_ANALYSIS_CTOR(CMS_2016_Viesturs_new);
    enum Reconstruction { CHARGED = 0, ALL = 1 };
    enum Flavor { INCL = 0, BOTTOM = 1, QUARK = 2, GLUON = 3 };  

    void init()
    {
      printf("*** running analysis CMS_2016_Viesturs_new ***\n");

      // Cuts
      particle_cut         = (Cuts::abseta < 5.0 && Cuts::pT >  0.0*GeV);
      lepton_cut           = (Cuts::abseta < 2.1 && Cuts::pT > 30.0*GeV);
      // lepton_cut           = (Cuts::abseta < 2.5 && Cuts::pT > 15.0*GeV);
      jet_cut              = (Cuts::abseta < 2.4 && Cuts::pT > 30.0*GeV);
      //      veto_lepton_cut      = (Cuts::abseta < 2.5 && Cuts::pT > 15.0*GeV);

      // Generic final state
      FinalState fs(particle_cut);

      // Dressed leptons
      ChargedLeptons charged_leptons(fs);
      IdentifiedFinalState photons(fs);
      photons.acceptIdPair(PID::PHOTON);


      PromptFinalState prompt_leptons(charged_leptons);
      prompt_leptons.acceptMuonDecays(true);
      prompt_leptons.acceptTauDecays(true);


      PromptFinalState prompt_photons(photons);
      prompt_photons.acceptMuonDecays(true);
      prompt_photons.acceptTauDecays(true);

      // NB. useDecayPhotons=true allows for photons with tau ancestor; photons from hadrons are vetoed by the PromptFinalState;
      DressedLeptons dressed_leptons(prompt_photons, prompt_leptons, 0.1, lepton_cut, true);
      declare(dressed_leptons, "DressedLeptons");



      // Projection for jets
      VetoedFinalState fsForJets(fs);
      fsForJets.addVetoOnThisFinalState(dressed_leptons);
      declare(FastJets(fsForJets, FastJets::ANTIKT, 0.4,
		       JetAlg::Muons::ALL, JetAlg::Invisibles::NONE), "Jets");

      // Booking of histograms
      const char *chargetitle[2] = {"all", "charged"};
      for (unsigned char chargeind = 0; chargeind < 1; ++ chargeind) { 
	char buffer [20];
	sprintf(buffer, "pull_angle_%s", chargetitle[chargeind]);
	printf("%s\n", buffer);
	book(_h[chargeind], buffer);
    
      }
      book(_hsel, "gen_selection");
    }

    void analyze(const Event& event) 
    {
      static unsigned long eventind = 0;
      // getchar();
      // printf("*****\nevent %lu\n", eventind);
      eventind ++;
      // select ttbar -> lepton+jets
      bool gen_singleLepton          = false;
      bool gen_singleLepton4Jets     = false;
      bool gen_singleLepton4Jets2b   = false;
      bool gen_singleLepton4Jets2b2W = false;
      const vector<DressedLepton> & leptons = applyProjection<DressedLeptons>(event, "DressedLeptons").dressedLeptons();
      int nsel_leptons = 0;
      for (const DressedLepton& lepton : leptons) {
	// printf("lepton pt %f eta %f\n", lepton.pt(), lepton.eta()); 
	if (lepton.pt() > 30.0 and lepton.eta() < 2.1) {
	  
	  nsel_leptons += 1; 
	}
	else{
	  printf("found veto lepton at event %lu\n", eventind);
	  vetoEvent;
	} // found veto lepton
      }
      
      if (nsel_leptons == 1){
	gen_singleLepton = true;
	_hsel -> fill(0);
      }
      if (not gen_singleLepton){
	vetoEvent;
      }
      const Jets all_jets = applyProjection<FastJets>(event, "Jets").jetsByPt(jet_cut);
      if (all_jets.size() >= 4){
	gen_singleLepton4Jets = true;
	_hsel -> fill(0);
	_hsel -> fill(1);
      }
      if (not gen_singleLepton4Jets){
	vetoEvent;
      }
	
      // categorize jets
      int nsel_bjets = 0;
      int nsel_wjets = 0;
      Jets jets[4];
      for (const Jet & jet : all_jets) {
	// check for jet-lepton overlap -> do not consider for selection
	if (deltaR(jet, leptons[0]) < 0.4) 
	  continue;

	bool overlap = false;
	bool w_jet   = false;
	for (const Jet& jet2 : all_jets) {
	  if (& jet == & jet2) 
	    continue;
	  // check for jet-jet overlap -> do not consider for analysis
	  // if (deltaR(jet, jet2) < 0.8)
	  //   overlap = true;
	  // check for W candidate
	  if (jet.bTagged() or jet2.bTagged()) 
	    continue;
	  FourMomentum w_cand = jet.momentum() + jet2.momentum();
	  if (abs(w_cand.mass() - 80.4) < 15.0) 
	    w_jet = true;
	}

	// count jets for event selection

	// jets for analysis
	if (jet.abseta() > 2.4 or overlap) 
	  continue;

	if (jet.bTagged()) {
	  nsel_bjets += 1;
	  jets[BOTTOM].push_back(jet);
	} else if (w_jet) {
	  jets[QUARK].push_back(jet);
	  nsel_wjets += 1;
	} else {
	  jets[GLUON].push_back(jet);
	}
      }

      if (nsel_bjets == 2){
	gen_singleLepton4Jets2b = true;
	_hsel -> fill(0);
	_hsel -> fill(1);
	_hsel -> fill(2);
      }
      if (not gen_singleLepton4Jets2b){
	vetoEvent;
      }
	
      if (nsel_wjets == 2){
	gen_singleLepton4Jets2b2W = true; 
	_hsel -> fill(0);
	_hsel -> fill(1);
	_hsel -> fill(2);
	_hsel -> fill(3);
      }
      if (not gen_singleLepton4Jets2b2W){
	vetoEvent;
      }

      // substructure analysis
      // no loop over incl jets -> more loc but faster
      for (unsigned char jind = 1; jind < 4; ++jind) {
	for (const Jet& jet : jets[jind]) {
	  // apply cuts on constituents
	  vector<PseudoJet> particles[2];
	  for (const Particle& p : jet.particles(Cuts::pT > 1.0*GeV)) {
	    particles[ALL].push_back( PseudoJet(p.px(), p.py(), p.pz(), p.energy()) );
	    if (p.charge3() != 0)
	      particles[CHARGED].push_back( PseudoJet(p.px(), p.py(), p.pz(), p.energy()) );
	  }

	  if (particles[CHARGED].size() == 0) continue;

	  // recluster with C/A and anti-kt+WTA
	}
      }
      std::vector<Jet *> jets_sorted[4];

      for (Jets::iterator it = jets[QUARK].begin(); it != jets[QUARK].end(); ++it ){
	jets_sorted[QUARK].push_back(&*it);
      }

      bool sorted = false;
      while (not sorted){
	sorted = true;
	for (std::vector<Jet *>::iterator it = jets_sorted[QUARK].begin(); it != jets_sorted[QUARK].end() -1 ; ++ it){
	  if ((*it) -> pt() < (*(it + 1)) -> pt()){
	    
	    Jet * swap = *(it + 1);
	    *(it) = *(it +1) ;
	    *(it + 1 ) = swap;
	    sorted = false;
	  }
	} 
      }
      
      if (deltaR(*jets_sorted[QUARK][0], *jets_sorted[QUARK][1]) > 1.0  )	{
	
	const double pull_angle = fabs(CalculatePullAngle(*jets_sorted[QUARK][0], *jets_sorted[QUARK][1], false));
	//      printf("filling pull_angle %f\n", pull_angle);
	_h[0] -> fill(pull_angle / Rivet::PI);
      }
	  
    }

  

    void finalize(){
      double norm = (sumOfWeights() != 0) ? crossSection()/picobarn/sumOfWeights() : 1.0;

      for (unsigned chargeind = 0; chargeind < 1; ++ chargeind){
	printf("number of entries %f\n", _h[chargeind] -> numEntries());
	printf("sumOfweights() %f\n", sumOfWeights());
	printf("crossSection() %f\n", crossSection());
	printf("picobarn %f femtobar %f\n", picobarn, femtobarn);

	printf("norm %f\n", norm);
	scale(_h[0],      norm);

	//	normalize(_h[chargeind]);
	//	normalize(_h[chargeind], 1.0, false);

      }
      scale(_hsel,      norm);
      
    }
  private:
    double deltaR(PseudoJet j1, PseudoJet j2) {
      double deta = j1.eta() - j2.eta();
      double dphi = j1.delta_phi_to(j2);
      return sqrt(deta*deta + dphi*dphi);
    }

    Vector3 CalculatePull(Jet& jet, bool &isCharged) {
      Vector3 pull(0.0, 0.0, 0.0);
      double PT = jet.pT();
      Particles& constituents = jet.particles();
      Particles charged_constituents;
      if (isCharged) {
	for (Particle & p : constituents) {
	  if (p.charge3() != 0)  
	    charged_constituents += p;
	}
	constituents = charged_constituents;
      }
      // calculate axis
      FourMomentum axis;
      for (Particle& p : constituents)  
	axis += p.momentum();
      Vector3 J(axis.rap(), axis.phi(MINUSPI_PLUSPI), 0.0);
      // calculate pull
      for (Particle & p : constituents) {
	Vector3 ri = Vector3(p.rap(), p.phi(MINUSPI_PLUSPI), 0.0) - J;
	while (ri.y() >  Rivet::PI) ri.setY(ri.y() - Rivet::TWOPI);
	while (ri.y() < -Rivet::PI) ri.setY(ri.y() + Rivet::TWOPI);
	pull.setX(pull.x() + (ri.mod() * ri.x() * p.pT()) / PT);
	pull.setY(pull.y() + (ri.mod() * ri.y() * p.pT()) / PT);
      }
      return pull;
    }

    double CalculatePullAngle(Jet& jet1, Jet& axisjet, bool isCharged) {
      // printf("jet1 px %f py %f, pz %f, E %f\n", jet1.px(), jet1.py(), jet1.pz(), jet1.E() );
      // printf("aixsjet px %f py %f, pz %f, E %f\n", axisjet.px(), axisjet.py(), axisjet.pz(), axisjet.E() );
      Vector3 pull_vector = CalculatePull(jet1, isCharged);
      // printf("pull_vector px %f, py %f, pz %f\n", pull_vector.x(), pull_vector.y(), pull_vector.z()); 
      pull_vector = Vector3(1000.*pull_vector.x(), 1000.*pull_vector.y(), 0.0);
      double drap = axisjet.rap() - jet1.rap();
            double dphi = axisjet.phi(MINUSPI_PLUSPI) - jet1.phi(MINUSPI_PLUSPI);
      // double dphi = axisjet.phi() - jet1.phi();
      Vector3 j2_vector(drap, dphi, 0.0);
      //return deltaPhi(pull_vector, j2_vector);
            return mapAngleMPiToPi(deltaPhi(pull_vector, j2_vector));
    }

    Cut particle_cut, lepton_cut, jet_cut;
    Histo1DPtr _h[2];
    Histo1DPtr _hsel;
  };
  // The hook for the plugin system
    
  DECLARE_RIVET_PLUGIN(CMS_2016_Viesturs_new);
}

