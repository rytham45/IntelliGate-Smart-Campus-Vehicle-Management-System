package com.liftley.intelligate.data

import android.util.Base64
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.database.DataSnapshot
import com.google.firebase.database.DatabaseError
import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ServerValue
import com.google.firebase.database.ValueEventListener
import com.liftley.intelligate.domain.VerificationRepository
import com.liftley.intelligate.domain.VerificationUpdate
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import kotlin.time.Duration.Companion.milliseconds

class FirebaseVerificationRepository(
    authProvider: () -> FirebaseAuth,
    databaseProvider: () -> FirebaseDatabase,
) : VerificationRepository {
    private val auth by lazy(authProvider)
    private val database by lazy(databaseProvider)

    override fun verify(requestId: String, jpeg: ByteArray): Flow<VerificationUpdate> {
        require(jpeg.size <= 500_000) { "Photo exceeds the 500 KB upload limit." }
        return submit(requestId, "scan_images", "image", Base64.encodeToString(jpeg, Base64.NO_WRAP))
    }

    private fun submit(requestId: String, tree: String, field: String, value: String): Flow<VerificationUpdate> = flow {
        emit(VerificationUpdate.Uploading)
        val uid = auth.currentUser?.uid ?: auth.signInAnonymously().await().user?.uid
            ?: error("Could not sign in.")
        val result = database.getReference("scan_results/$uid/$requestId")
        val image = database.getReference("$tree/$uid/$requestId")
        try {
            // Firebase removes these paths if this client's connection disappears.
            image.onDisconnect().removeValue().await()
            result.onDisconnect().removeValue().await()
            withTimeout(30_000.milliseconds) {
                image.setValue(mapOf(
                    field to value,
                    "created_at" to ServerValue.TIMESTAMP,
                )).await()
            }
            emit(VerificationUpdate.Processing)
            emitAll(callbackFlow {
                val listener = object : ValueEventListener {
                    override fun onDataChange(snapshot: DataSnapshot) {
                        if (!snapshot.exists()) return
                        runCatching {
                            val values = snapshot.value as? Map<*, *> ?: error("Invalid server response.")
                            ResultParser.parse(values)
                        }.onSuccess {
                            trySend(VerificationUpdate.Complete(it))
                            close()
                        }.onFailure { close(it) }
                    }
                    override fun onCancelled(error: DatabaseError) {
                        close(error.toException())
                    }
                }
                result.addValueEventListener(listener)
                awaitClose { result.removeEventListener(listener) }
            })
        } finally {
            // Runs on success, errors, timeout and cancellation. Offline cleanup also
            // needs the Python sweeper: an Android process cannot guarantee delivery.
            withContext(NonCancellable) {
                runCatching {
                    withTimeout(5_000.milliseconds) {
                        database.reference.updateChildren(mapOf(
                            "$tree/$uid/$requestId" to null,
                            "scan_results/$uid/$requestId" to null,
                        )).await()
                    }
                }
            }
        }
    }
}
