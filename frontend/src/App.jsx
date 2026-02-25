// src/App.jsx - Frontend React pour Agent Intent TMF921
import React, { useState } from 'react';
import { 
  Container, 
  Box, 
  Typography, 
  TextField, 
  Button, 
  Card, 
  CardContent,
  Stepper,
  Step,
  StepLabel,
  Alert,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Radio,
  RadioGroup,
  FormControlLabel,
  FormControl,
  Chip,
  Grid,
  Paper,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SendIcon from '@mui/icons-material/Send';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import DownloadIcon from '@mui/icons-material/Download';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import LinkIcon from '@mui/icons-material/Link';
import AccountTreeIcon from '@mui/icons-material/AccountTree';

// Configuration de l'API
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const steps = [
  'Classification',
  'Décomposition',
  'Validation',
  'Clarification/Alternatives',
  'Génération Intent'
];

function App() {
  // États du workflow
  const [activeStep, setActiveStep] = useState(0);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState(''); // ✅ NOUVEAU : label précis du spinner
  const [error, setError] = useState(null);
  
  // États des données
  const [classification, setClassification] = useState(null);
  const [decomposition, setDecomposition] = useState(null);
  const [selectedServices, setSelectedServices] = useState({});
  const [validatedServices, setValidatedServices] = useState([]);
  const [clarificationResponse, setClarificationResponse] = useState('');
  const [alternatives, setAlternatives] = useState([]);
  const [finalIntent, setFinalIntent] = useState(null);
  
  // État de la conversation
  const [conversationState, setConversationState] = useState({
    user_request_original: '',
    services_valides: {},
    services_identifies: [],
    historique: []
  });

  // Réinitialiser le workflow
  const resetWorkflow = () => {
    setActiveStep(0);
    setUserInput('');
    setError(null);
    setClassification(null);
    setDecomposition(null);
    setSelectedServices({});
    setValidatedServices([]);
    setClarificationResponse('');
    setAlternatives([]);
    setFinalIntent(null);
    setLoadingLabel('');
    setConversationState({
      user_request_original: '',
      services_valides: {},
      services_identifies: [],
      historique: []
    });
  };

  // Étape 1 : Classification
  const handleClassification = async () => {
    if (!userInput.trim()) {
      setError('Veuillez entrer une demande');
      return;
    }

    setLoading(true);
    setLoadingLabel('Classification en cours...');
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: userInput })
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Erreur de classification');

      setClassification(data);

      if (data.type === 'TELECOM') {
        // Passer directement à la décomposition
        await handleDecomposition();
      } else {
        // Salutation ou hors sujet
        setActiveStep(1);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingLabel('');
    }
  };

  // Étape 2 : Décomposition
  const handleDecomposition = async () => {
    setLoadingLabel('Décomposition en cours...');
    // loading est déjà true ici (appelé depuis handleClassification)

    try {
      const response = await fetch(`${API_BASE_URL}/api/decompose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: userInput })
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Erreur de décomposition');

      setDecomposition(data);
      setConversationState(prev => ({
        ...prev,
        user_request_original: userInput,
        services_identifies: data.services_identifies,
        historique: [...prev.historique, `Demande: ${userInput}`]
      }));
      setActiveStep(2);
    } catch (err) {
      setError(err.message);
    }
  };

  // Étape 3 : Validation des services
  const handleValidation = async () => {
    if (Object.keys(selectedServices).length === 0) {
      setError('Veuillez sélectionner au moins un service');
      return;
    }

    setLoading(true);
    setLoadingLabel('Validation en cours...');
    setError(null);

    try {
      // Construire les services validés
      const validated = {};
      Object.entries(selectedServices).forEach(([serviceName, serviceId]) => {
        const candidates = decomposition.candidates[serviceName];
        const candidate = candidates?.find(c => c.service_id === serviceId);
        if (candidate) {
          validated[serviceName] = candidate;
        }
      });

      setConversationState(prev => ({
        ...prev,
        services_valides: validated,
        // ✅ Mettre à jour les services identifiés avec la décomposition courante
        services_identifies: decomposition.services_identifies
      }));

      setValidatedServices(Object.keys(validated));

      // Vérifier si tous les services ont été validés
      const allServicesValidated = decomposition.services_identifies.every(
        service => selectedServices[service.nom]
      );

      if (allServicesValidated) {
        await generateIntent(validated, decomposition.services_identifies);
      } else {
        setActiveStep(3);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingLabel('');
    }
  };

  // Étape 4 : Clarification
  const handleClarification = async () => {
    if (!clarificationResponse.trim()) {
      setError('Veuillez répondre à la question');
      return;
    }

    setLoading(true);
    setLoadingLabel('Analyse en cours...'); // ✅ NOUVEAU : feedback clair
    setError(null);

    try {
      const refusedServices = decomposition.services_identifies
        .filter(s => !selectedServices[s.nom])
        .map(s => s.nom);

      // ✅ CORRECTION : on envoie aussi les données complètes des services validés
      //    et la liste des services identifiés précédents pour permettre la fusion côté API
      const response = await fetch(`${API_BASE_URL}/api/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_clarification: clarificationResponse,
          services_valides_noms: validatedServices,
          services_refuses: refusedServices,
          original_request: userInput,
          services_valides_data: conversationState.services_valides,
          services_identifies_precedents: decomposition.services_identifies
        })
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Erreur de clarification');

      // ✅ CORRECTION : la réponse contient déjà la liste fusionnée (validés + nouveaux)
      //    On met à jour la décomposition avec cette liste complète
      setDecomposition(data);

      // ✅ CORRECTION : pré-sélectionner automatiquement les services déjà validés
      //    pour que l'utilisateur n'ait pas à les re-sélectionner
      if (data.pre_validated_services && data.pre_validated_services.length > 0) {
        const preSelected = {};
        data.pre_validated_services.forEach(svcNom => {
          // Retrouver le service_id depuis les candidats déjà validés
          const existingCandidate = conversationState.services_valides[svcNom];
          if (existingCandidate) {
            preSelected[svcNom] = existingCandidate.service_id;
          } else if (data.candidates[svcNom]?.[0]) {
            // Fallback : premier candidat de la liste fusionnée
            preSelected[svcNom] = data.candidates[svcNom][0].service_id;
          }
        });
        setSelectedServices(preSelected);
      } else {
        setSelectedServices({});
      }

      // ✅ Mettre à jour le conversationState avec les services identifiés mis à jour
      setConversationState(prev => ({
        ...prev,
        services_identifies: data.services_identifies,
        historique: [
          ...prev.historique,
          `Clarification: ${clarificationResponse}`
        ]
      }));

      setClarificationResponse('');
      setActiveStep(2); // Retour à la validation
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingLabel('');
    }
  };

  // Étape 4bis : Recommandation d'alternatives
  const handleAlternatives = async () => {
    setLoading(true);
    setLoadingLabel('Recherche d\'alternatives...');
    setError(null);

    try {
      const refusedServices = decomposition.services_identifies
        .filter(s => !selectedServices[s.nom])
        .map(s => s.nom);

      const response = await fetch(`${API_BASE_URL}/api/alternatives`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          services_refuses: refusedServices,
          services_valides: validatedServices,
          historique: conversationState.historique
        })
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Erreur de recommandation');

      setAlternatives(data.alternatives);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingLabel('');
    }
  };

  // Étape 5 : Génération de l'Intent TMF921
  const generateIntent = async (servicesValides = null, servicesIdentifies = null) => {
    setLoading(true);
    setLoadingLabel('Génération de l\'Intent TMF921...');
    setError(null);

    try {
      const validated = servicesValides || conversationState.services_valides;
      const identified = servicesIdentifies || conversationState.services_identifies;

      const response = await fetch(`${API_BASE_URL}/api/generate-intent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          services_valides: validated,
          services_identifies: identified,
          user_request_original: conversationState.user_request_original
        })
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Erreur de génération');

      setFinalIntent(data.intent);
      setActiveStep(4);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingLabel('');
    }
  };

  // Télécharger l'intent JSON
  const downloadIntent = () => {
    if (!finalIntent) return;

    const blob = new Blob([JSON.stringify(finalIntent, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `intent_${finalIntent.name}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Score color helper
  const getScoreColor = (score) => {
    if (score >= 0.6) return 'success';
    if (score >= 0.4) return 'warning';
    return 'error';
  };

  // ✅ NOUVEAU : composant pour afficher les dépendances d'un candidat
  const DependenciesPanel = ({ dependencies }) => {
    if (!dependencies || dependencies.length === 0) return null;

    return (
      <Box sx={{ mt: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
          <AccountTreeIcon fontSize="small" color="action" />
          <Typography variant="caption" fontWeight="bold" color="text.secondary">
            Dépendances CFSS ({dependencies.length})
          </Typography>
        </Box>
        <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'info.50', borderColor: 'info.200' }}>
          <List dense disablePadding>
            {dependencies.map((dep, idx) => (
              <ListItem key={dep.id || idx} disablePadding sx={{ py: 0.25 }}>
                <ListItemIcon sx={{ minWidth: 24 }}>
                  <LinkIcon fontSize="small" color="info" />
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Typography variant="body2" fontWeight="medium">
                        {dep.name}
                      </Typography>
                      <Chip
                        label={`v${dep.version}`}
                        size="small"
                        variant="outlined"
                        color="info"
                        sx={{ height: 18, '& .MuiChip-label': { px: 0.75, fontSize: '0.65rem' } }}
                      />
                      <Typography variant="caption" color="text.disabled">
                        {dep.id}
                      </Typography>
                    </Box>
                  }
                />
              </ListItem>
            ))}
          </List>
        </Paper>
      </Box>
    );
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4, textAlign: 'center' }}>
        <Typography variant="h3" component="h1" gutterBottom>
          🤖 Agent Intent-Driven 5G - TMF921
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Génération automatique d'Intent TMF921 depuis langage naturel
        </Typography>
      </Box>

      {/* ✅ NOUVEAU : bannière de chargement globale avec label précis */}
      {loading && (
        <Alert
          severity="info"
          icon={<CircularProgress size={18} color="inherit" />}
          sx={{ mb: 3, fontWeight: 500 }}
        >
          {loadingLabel || 'Traitement en cours...'}
        </Alert>
      )}

      {/* Stepper */}
      <Box sx={{ mb: 4 }}>
        <Stepper activeStep={activeStep} alternativeLabel>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Box>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Step 0: Input */}
      {activeStep === 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              1️⃣ Exprimez votre besoin
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={6}
              placeholder="Exemple : Je veux une caméra 5G avec analyse vidéo dans Paris, débit minimum 100 Mbps, avec alerte SMS en cas de détection d'intrusion."
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              sx={{ mb: 2 }}
            />
            <Button
              variant="contained"
              fullWidth
              size="large"
              endIcon={loading ? <CircularProgress size={20} color="inherit" /> : <SendIcon />}
              onClick={handleClassification}
              disabled={loading || !userInput.trim()}
            >
              {loading ? loadingLabel || 'Analyse en cours...' : 'Analyser la demande'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 1: Classification Result */}
      {activeStep === 1 && classification && classification.type !== 'TELECOM' && (
        <Card>
          <CardContent>
            <Alert severity={classification.type === 'GREETING' ? 'info' : 'warning'} sx={{ mb: 2 }}>
              {classification.message}
            </Alert>
            <Button
              variant="outlined"
              startIcon={<RestartAltIcon />}
              onClick={resetWorkflow}
            >
              Nouvelle demande
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Validation */}
      {activeStep === 2 && decomposition && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              2️⃣ Validation de la décomposition
            </Typography>

            {validatedServices.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Alert severity="success">
                  ✅ {validatedServices.length} service(s) déjà validé(s) — pré-sélectionnés ci-dessous
                </Alert>
                {validatedServices.map(name => (
                  <Chip key={name} label={name} color="success" sx={{ m: 0.5 }} />
                ))}
                <Divider sx={{ my: 2 }} />
              </Box>
            )}

            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              📋 Services identifiés
            </Typography>

            {decomposition.services_identifies.map((service) => {
              const candidates = decomposition.candidates[service.nom] || [];
              const hasLowScores = candidates.every(c => c.score < 0.4);
              const isPreValidated = validatedServices.includes(service.nom);

              return (
                <Accordion
                  key={service.nom}
                  sx={{
                    mb: 2,
                    border: isPreValidated ? '1px solid' : undefined,
                    borderColor: isPreValidated ? 'success.light' : undefined
                  }}
                  defaultExpanded={!isPreValidated}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', width: '100%', gap: 1 }}>
                      {isPreValidated && <CheckCircleIcon color="success" fontSize="small" />}
                      <Typography sx={{ flexGrow: 1, fontWeight: 'bold' }}>
                        {service.nom}
                      </Typography>
                      {isPreValidated && (
                        <Chip label="Déjà validé" color="success" size="small" variant="outlined" />
                      )}
                      {selectedServices[service.nom] && !isPreValidated && (
                        <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                      )}
                      {hasLowScores && !isPreValidated && (
                        <Chip label="Scores faibles" color="warning" size="small" />
                      )}
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" color="text.secondary" paragraph>
                      <strong>Raison :</strong> {service.raison}
                    </Typography>

                    {service.proprietes && Object.keys(service.proprietes).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: 'grey.50' }}>
                        <Typography variant="subtitle2" gutterBottom>
                          Propriétés requises :
                        </Typography>
                        {Object.entries(service.proprietes).map(([key, value]) => (
                          <Typography key={key} variant="body2">
                            • <strong>{key}</strong>: {JSON.stringify(value)}
                          </Typography>
                        ))}
                      </Paper>
                    )}

                    {candidates.length > 0 ? (
                      <FormControl component="fieldset" fullWidth>
                        <RadioGroup
                          value={selectedServices[service.nom] || ''}
                          onChange={(e) => setSelectedServices({
                            ...selectedServices,
                            [service.nom]: e.target.value
                          })}
                        >
                          {candidates.map((candidate) => (
                            <Paper
                              key={candidate.service_id}
                              variant="outlined"
                              sx={{
                                p: 2,
                                mb: 1,
                                bgcolor: selectedServices[service.nom] === candidate.service_id
                                  ? 'success.50'
                                  : undefined,
                                borderColor: selectedServices[service.nom] === candidate.service_id
                                  ? 'success.light'
                                  : undefined
                              }}
                            >
                              <FormControlLabel
                                value={candidate.service_id}
                                control={<Radio />}
                                label={
                                  <Box>
                                    <Typography variant="body1" fontWeight="bold">
                                      {candidate.name}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary">
                                      {candidate.description}
                                    </Typography>
                                    <Chip
                                      label={`Score: ${candidate.score.toFixed(3)}`}
                                      color={getScoreColor(candidate.score)}
                                      size="small"
                                      sx={{ mt: 1 }}
                                    />
                                    {/* ✅ CORRECTION : affichage complet des dépendances */}
                                    <DependenciesPanel dependencies={candidate.dependencies} />
                                  </Box>
                                }
                              />
                            </Paper>
                          ))}
                        </RadioGroup>
                      </FormControl>
                    ) : (
                      <Alert severity="warning">
                        Aucun candidat trouvé avec un score suffisant
                      </Alert>
                    )}
                  </AccordionDetails>
                </Accordion>
              );
            })}

            <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                fullWidth
                onClick={handleValidation}
                disabled={loading || Object.keys(selectedServices).length === 0}
                endIcon={loading ? <CircularProgress size={20} color="inherit" /> : null}
              >
                {loading ? loadingLabel || 'Validation...' : 'Valider la sélection'}
              </Button>
              <Button
                variant="outlined"
                onClick={resetWorkflow}
                startIcon={<RestartAltIcon />}
              >
                Recommencer
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Clarification/Alternatives */}
      {activeStep === 3 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              3️⃣ Clarification ou Alternatives
            </Typography>

            <Alert severity="info" sx={{ mb: 3 }}>
              Certains services n'ont pas pu être validés. Vous pouvez :
              <ul>
                <li>Clarifier vos besoins pour affiner la recherche</li>
                <li>Demander des alternatives</li>
                <li>Continuer avec les services déjà validés</li>
              </ul>
            </Alert>

            {validatedServices.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" gutterBottom>
                  ✅ Services validés ({validatedServices.length}) :
                </Typography>
                {validatedServices.map(name => (
                  <Chip key={name} label={name} color="success" sx={{ m: 0.5 }} />
                ))}
              </Box>
            )}

            <Typography variant="subtitle2" gutterBottom>
              ❌ Services non trouvés :
            </Typography>
            {decomposition.services_identifies
              .filter(s => !selectedServices[s.nom])
              .map(s => (
                <Chip key={s.nom} label={s.nom} color="error" sx={{ m: 0.5 }} />
              ))}

            <Divider sx={{ my: 3 }} />

            <Typography variant="subtitle1" gutterBottom fontWeight="bold">
              Option 1 : Clarifier vos besoins
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={3}
              placeholder="Exemple : Je préfère utiliser la 5G plutôt que le WiFi..."
              value={clarificationResponse}
              onChange={(e) => setClarificationResponse(e.target.value)}
              sx={{ mb: 2 }}
              disabled={loading}
            />
            {/* ✅ CORRECTION : bouton avec spinner + label explicite pendant le chargement */}
            <Button
              variant="contained"
              fullWidth
              onClick={handleClarification}
              disabled={loading || !clarificationResponse.trim()}
              endIcon={loading && loadingLabel === 'Analyse en cours...'
                ? <CircularProgress size={20} color="inherit" />
                : null
              }
              sx={{ mb: 3 }}
            >
              {loading && loadingLabel === 'Analyse en cours...'
                ? 'Analyse en cours...'
                : 'Clarifier'
              }
            </Button>

            <Divider sx={{ my: 3 }} />

            <Typography variant="subtitle1" gutterBottom fontWeight="bold">
              Option 2 : Demander des alternatives
            </Typography>
            <Button
              variant="outlined"
              fullWidth
              onClick={handleAlternatives}
              disabled={loading}
              endIcon={loading && loadingLabel === "Recherche d'alternatives..."
                ? <CircularProgress size={20} color="inherit" />
                : null
              }
              sx={{ mb: 2 }}
            >
              {loading && loadingLabel === "Recherche d'alternatives..."
                ? "Recherche d'alternatives..."
                : 'Proposer des alternatives'
              }
            </Button>

            {alternatives.length > 0 && (
              <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Services alternatifs proposés :
                </Typography>
                {alternatives.map(alt => (
                  <Chip key={alt} label={alt} sx={{ m: 0.5 }} />
                ))}
              </Paper>
            )}

            <Divider sx={{ my: 3 }} />

            <Typography variant="subtitle1" gutterBottom fontWeight="bold">
              Option 3 : Terminer avec les services validés
            </Typography>
            <Button
              variant="contained"
              color="success"
              fullWidth
              onClick={() => generateIntent()}
              disabled={loading || validatedServices.length === 0}
              endIcon={loading && loadingLabel.includes('Intent')
                ? <CircularProgress size={20} color="inherit" />
                : null
              }
            >
              {loading && loadingLabel.includes('Intent')
                ? "Génération de l'Intent..."
                : "Générer l'Intent avec services validés"
              }
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Final Intent */}
      {activeStep === 4 && finalIntent && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom color="success.main">
              ✅ Intent TMF921 généré avec succès !
            </Typography>

            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={4}>
                <Paper sx={{ p: 2, textAlign: 'center' }}>
                  <Typography variant="h4">{Object.keys(conversationState.services_valides).length}</Typography>
                  <Typography variant="body2" color="text.secondary">Services</Typography>
                </Paper>
              </Grid>
              <Grid item xs={4}>
                <Paper sx={{ p: 2, textAlign: 'center' }}>
                  <Typography variant="h5">{finalIntent.name}</Typography>
                  <Typography variant="body2" color="text.secondary">Nom</Typography>
                </Paper>
              </Grid>
              <Grid item xs={4}>
                <Paper sx={{ p: 2, textAlign: 'center' }}>
                  <Typography variant="h4">{finalIntent.characteristic?.length || 0}</Typography>
                  <Typography variant="body2" color="text.secondary">Propriétés</Typography>
                </Paper>
              </Grid>
            </Grid>

            <Typography variant="subtitle1" gutterBottom fontWeight="bold">
              📦 Services validés
            </Typography>
            {validatedServices.map(name => (
              <Chip key={name} label={name} color="success" sx={{ m: 0.5 }} />
            ))}

            <Divider sx={{ my: 3 }} />

            <Typography variant="subtitle1" gutterBottom fontWeight="bold">
              📄 Intent TMF921 complet
            </Typography>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                mb: 2,
                bgcolor: 'grey.50',
                maxHeight: 400,
                overflow: 'auto'
              }}
            >
              <pre style={{ margin: 0, fontSize: '0.85rem' }}>
                {JSON.stringify(finalIntent, null, 2)}
              </pre>
            </Paper>

            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                startIcon={<DownloadIcon />}
                onClick={downloadIntent}
                fullWidth
              >
                Télécharger JSON
              </Button>
              <Button
                variant="outlined"
                startIcon={<RestartAltIcon />}
                onClick={resetWorkflow}
                fullWidth
              >
                Nouvelle demande
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Container>
  );
}

export default App;
