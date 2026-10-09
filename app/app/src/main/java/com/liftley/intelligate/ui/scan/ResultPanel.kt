package com.liftley.intelligate.ui.scan

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.liftley.intelligate.R
import com.liftley.intelligate.domain.Decision
import com.liftley.intelligate.domain.VerificationResult
import com.liftley.intelligate.ui.components.GateIcon
import com.liftley.intelligate.ui.components.GateSymbol

@Composable
fun ResultPanel(result: VerificationResult) {
    val colors = MaterialTheme.colorScheme
    val (background, foreground) = when (result.decision) {
        Decision.APPROVED -> colors.primaryContainer to colors.onPrimaryContainer
        Decision.DENIED -> colors.errorContainer to colors.onErrorContainer
        Decision.REVIEW -> colors.tertiaryContainer to colors.onTertiaryContainer
    }
    Surface(shape = MaterialTheme.shapes.extraLarge, color = background, contentColor = foreground) {
        Column(
            Modifier.fillMaxWidth().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GateIcon(
                if (result.decision == Decision.REVIEW) GateSymbol.CAMERA else GateSymbol.SHIELD,
                Modifier.size(56.dp),
            )
            Text(stringResource(when (result.decision) {
                Decision.APPROVED -> R.string.approved
                Decision.DENIED -> R.string.not_approved
                Decision.REVIEW -> R.string.unreadable_plate
            }), style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center)
            result.plateNumber?.let {
                Text(it, style = MaterialTheme.typography.headlineSmall,
                    fontFamily = FontFamily.Monospace, textAlign = TextAlign.Center)
            }
            Text(
                stringResource(when (result.decision) {
                    Decision.APPROVED -> R.string.approval_explanation
                    Decision.DENIED -> R.string.denial_explanation
                    Decision.REVIEW -> R.string.retake_hint
                }),
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
            )
            if (result.name != null || result.role != null) {
                HorizontalDivider(color = foreground.copy(alpha = 0.2f))
                result.name?.let {
                    Text(stringResource(R.string.vehicle_owner, it), textAlign = TextAlign.Center)
                }
                result.role?.let {
                    Text(stringResource(R.string.vehicle_role, it.replaceFirstChar(Char::titlecase)),
                        textAlign = TextAlign.Center)
                }
            }
            result.hasPass?.let {
                Text(stringResource(if (it) R.string.has_pass else R.string.no_pass))
            }
            if (result.decision == Decision.DENIED) {
                Text(stringResource(R.string.denial_next_step),
                    style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
            }
        }
    }
}
